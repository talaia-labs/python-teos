from uuid import uuid4
from queue import Queue
from threading import Thread

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from pisa.logger import Logger
from pisa.cleaner import Cleaner
from pisa.responder import Responder
from pisa.cryptographer import Cryptographer
from pisa.block_processor import BlockProcessor
from pisa.utils.zmq_subscriber import ZMQHandler
from pisa.conf import EXPIRY_DELTA, MAX_APPOINTMENTS, PISA_SECRET_KEY

logger = Logger("Watcher")


class Watcher:
    def __init__(self, db_manager, pisa_sk_file=PISA_SECRET_KEY, responder=None, max_appointments=MAX_APPOINTMENTS):
        self.appointments = dict()
        self.locator_uuid_map = dict()
        self.asleep = True
        self.block_queue = Queue()
        self.max_appointments = max_appointments
        self.zmq_subscriber = None
        self.db_manager = db_manager

        if not isinstance(responder, Responder):
            self.responder = Responder(db_manager)

        if pisa_sk_file is None:
            raise ValueError("No signing key provided. Please fix your pisa.conf")
        else:
            with open(PISA_SECRET_KEY, "r") as key_file:
                secret_key_pem = key_file.read().encode("utf-8")
                self.signing_key = load_pem_private_key(secret_key_pem, password=None, backend=default_backend())

    @staticmethod
    def compute_locator(tx_id):
        return tx_id[:32]

    def sign_appointment(self, appointment):
        data = appointment.serialize()
        return self.signing_key.sign(data, ec.ECDSA(hashes.SHA256()))

    def add_appointment(self, appointment):
        # Rationale:
        # The Watcher will analyze every received block looking for appointment matches. If there is no work
        # to do the watcher can go sleep (if appointments = {} then asleep = True) otherwise for every received block
        # the watcher will get the list of transactions and compare it with the list of appointments.
        # If the watcher is awake, every new appointment will just be added to the appointment list until
        # max_appointments is reached.

        if len(self.appointments) < self.max_appointments:
            # Appointments are identified by the locator: the sha256 of commitment txid (H(tx_id)).
            # Two different nodes may ask for appointments using the same commitment txid, what will result in a
            # collision in our appointments structure (and may be an attack surface). In order to avoid such collisions
            # we will identify every appointment with a uuid

            uuid = uuid4().hex
            self.appointments[uuid] = appointment

            if appointment.locator in self.locator_uuid_map:
                self.locator_uuid_map[appointment.locator].append(uuid)

            else:
                self.locator_uuid_map[appointment.locator] = [uuid]

            if self.asleep:
                self.asleep = False
                zmq_thread = Thread(target=self.do_subscribe)
                watcher = Thread(target=self.do_watch)
                zmq_thread.start()
                watcher.start()

                logger.info("Waking up")

            self.db_manager.store_watcher_appointment(uuid, appointment.to_json())
            self.db_manager.store_update_locator_map(appointment.locator, uuid)

            appointment_added = True

            logger.info("New appointment accepted.", locator=appointment.locator)

            signature = self.sign_appointment(appointment)
        else:
            appointment_added = False
            signature = None

            logger.info("Maximum appointments reached, appointment rejected.", locator=appointment.locator)

        return appointment_added, signature

    def do_subscribe(self):
        self.zmq_subscriber = ZMQHandler(parent="Watcher")
        self.zmq_subscriber.handle(self.block_queue)

    def do_watch(self):
        while len(self.appointments) > 0:
            block_hash = self.block_queue.get()
            logger.info("New block received", block_hash=block_hash)

            block = BlockProcessor.get_block(block_hash)

            if block is not None:
                txids = block.get("tx")

                logger.info("List of transactions.", txids=txids)

                expired_appointments = [
                    uuid
                    for uuid, appointment in self.appointments.items()
                    if block["height"] > appointment.end_time + EXPIRY_DELTA
                ]

                Cleaner.delete_expired_appointment(
                    expired_appointments, self.appointments, self.locator_uuid_map, self.db_manager
                )

                filtered_matches = self.filter_valid_matches(self.get_matches(txids))

                for uuid, filtered_match in filtered_matches.items():
                    # Errors decrypting the Blob will result in a None justice_txid
                    if filtered_match["valid_match"] is True:
                        logger.info(
                            "Notifying responder and deleting appointment.",
                            justice_txid=filtered_match["justice_txid"],
                            locator=filtered_match["locator"],
                            uuid=uuid,
                        )

                        self.responder.add_response(
                            uuid,
                            filtered_match["dispute_txid"],
                            filtered_match["justice_txid"],
                            filtered_match["justice_rawtx"],
                            self.appointments[uuid].end_time,
                            block_hash,
                        )

                    # Delete the appointment and update db
                    Cleaner.delete_completed_appointment(
                        filtered_match["locator"], uuid, self.appointments, self.locator_uuid_map, self.db_manager
                    )

                # Register the last processed block for the watcher
                self.db_manager.store_last_block_hash_watcher(block_hash)

        # Go back to sleep if there are no more appointments
        self.asleep = True
        self.zmq_subscriber.terminate = True
        self.block_queue = Queue()

        logger.info("No more pending appointments, going back to sleep")

    def get_matches(self, txids):
        potential_locators = {Watcher.compute_locator(txid): txid for txid in txids}

        # Check is any of the tx_ids in the received block is an actual match
        intersection = set(self.locator_uuid_map.keys()).intersection(potential_locators.keys())
        matches = {locator: potential_locators[locator] for locator in intersection}

        if len(matches) > 0:
            logger.info("List of matches", potential_matches=matches)

        else:
            logger.info("No matches found")

        return matches

    def filter_valid_matches(self, matches):
        filtered_matches = {}

        for locator, dispute_txid in matches.items():
            for uuid in self.locator_uuid_map[locator]:

                justice_rawtx = Cryptographer.decrypt(self.appointments[uuid].encrypted_blob, dispute_txid)
                justice_tx = BlockProcessor.decode_raw_transaction(justice_rawtx)

                if justice_tx is not None:
                    justice_txid = justice_tx.get("txid")
                    valid_match = True

                    logger.info("Match found for locator.", locator=locator, uuid=uuid, justice_txid=justice_txid)

                else:
                    justice_txid = None
                    valid_match = False

                filtered_matches[uuid] = {
                    "locator": locator,
                    "dispute_txid": dispute_txid,
                    "justice_txid": justice_txid,
                    "justice_rawtx": justice_rawtx,
                    "valid_match": valid_match,
                }

        return filtered_matches
