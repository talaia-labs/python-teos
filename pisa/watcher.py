from uuid import uuid4
from queue import Queue
from threading import Thread

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric import ec

from pisa.logger import Logger
from pisa.cleaner import Cleaner
from pisa.conf import EXPIRY_DELTA, MAX_APPOINTMENTS, PISA_SECRET_KEY
from pisa.responder import Responder
from pisa.block_processor import BlockProcessor
from pisa.utils.zmq_subscriber import ZMQHandler

logger = Logger("Watcher")


class Watcher:
    def __init__(self, db_manager, responder=None, max_appointments=MAX_APPOINTMENTS):
        self.appointments = dict()
        self.locator_uuid_map = dict()
        self.block_queue = None
        self.asleep = True
        self.max_appointments = max_appointments
        self.zmq_subscriber = None

        if not isinstance(responder, Responder):
            self.responder = Responder(db_manager)

        self.db_manager = db_manager

        if PISA_SECRET_KEY is None:
            raise ValueError("No signing key provided. Please fix your pisa.conf")
        else:
            with open(PISA_SECRET_KEY, "r") as key_file:
                secret_key_pem = key_file.read().encode("utf-8")
                self.signing_key = load_pem_private_key(secret_key_pem, password=None, backend=default_backend())

    def sign_appointment(self, appointment):
        data = appointment.to_json().encode("utf-8")
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
                self.block_queue = Queue()
                zmq_thread = Thread(target=self.do_subscribe)
                watcher = Thread(target=self.do_watch)
                zmq_thread.start()
                watcher.start()

                logger.info("Waking up")

            self.db_manager.store_watcher_appointment(uuid, appointment.to_json())

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
                txids = block.get('tx')

                logger.info("List of transactions.", txids=txids)

                expired_appointments = [uuid for uuid, appointment in self.appointments.items()
                                        if block["height"] > appointment.end_time + EXPIRY_DELTA]

                Cleaner.delete_expired_appointment(expired_appointments, self.appointments, self.locator_uuid_map,
                                                   self.db_manager)

                potential_matches = BlockProcessor.get_potential_matches(txids, self.locator_uuid_map)
                matches = BlockProcessor.get_matches(potential_matches, self.locator_uuid_map, self.appointments)

                for locator, uuid, dispute_txid, justice_txid, justice_rawtx in matches:
                    # Errors decrypting the Blob will result in a None justice_txid
                    if justice_txid is not None:
                        logger.info("Notifying responder and deleting appointment.", justice_txid=justice_txid,
                                    locator=locator, uuid=uuid)

                        self.responder.add_response(uuid, dispute_txid, justice_txid, justice_rawtx,
                                                    self.appointments[uuid].end_time, block_hash)

                    # Delete the appointment
                    appointment = self.appointments.pop(uuid)

                    # If there was only one appointment that matches the locator we can delete the whole list
                    if len(self.locator_uuid_map[locator]) == 1:
                        self.locator_uuid_map.pop(locator)
                    else:
                        # Otherwise we just delete the appointment that matches locator:appointment_pos
                        self.locator_uuid_map[locator].remove(uuid)

                    # DISCUSS: instead of deleting the appointment, we will mark it as triggered and delete it from both
                    #          the watcher's and responder's db after fulfilled
                    # Update appointment in the db
                    appointment.triggered = True
                    self.db_manager.store_watcher_appointment(uuid, appointment.to_json())

                    # Register the last processed block for the watcher
                    self.db_manager.store_last_block_watcher(block_hash)

        # Go back to sleep if there are no more appointments
        self.asleep = True
        self.zmq_subscriber.terminate = True

        logger.error("No more pending appointments, going back to sleep")
