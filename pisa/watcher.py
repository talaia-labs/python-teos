from uuid import uuid4
from queue import Queue
from threading import Thread

import common.cryptographer
from common.cryptographer import Cryptographer
from common.appointment import Appointment
from common.tools import compute_locator

from common.logger import Logger

from pisa import LOG_PREFIX
from pisa.cleaner import Cleaner
from pisa.block_processor import BlockProcessor

logger = Logger(actor="Watcher", log_name_prefix=LOG_PREFIX)
common.cryptographer.logger = Logger(actor="Cryptographer", log_name_prefix=LOG_PREFIX)


class Watcher:
    """
    The :class:`Watcher` is the class in charge to watch for channel breaches for the appointments accepted by the
    tower.

    The :class:`Watcher` keeps track of the accepted appointments in ``appointments`` and, for new received block,
    checks if any breach has happened by comparing the txids with the appointment locators. If a breach is seen, the
    :obj:`EncryptedBlob <common.encrypted_blob.EncryptedBlob>` of the corresponding appointment is decrypted and the data
    is passed to the :obj:`Responder <pisa.responder.Responder>`.

    If an appointment reaches its end with no breach, the data is simply deleted.

    The :class:`Watcher` receives information about new received blocks via the ``block_queue`` that is populated by the
    :obj:`ChainMonitor <pisa.chain_monitor.ChainMonitor>`.

    Args:
        db_manager (:obj:`DBManager <pisa.db_manager>`): a ``DBManager`` instance to interact with the database.
        sk_der (:obj:`bytes`): a DER encoded private key used to sign appointment receipts (signaling acceptance).
        config (:obj:`dict`): a dictionary containing all the configuration parameters. Used locally to retrieve
            ``MAX_APPOINTMENTS``  and ``EXPIRY_DELTA``.
        responder (:obj:`Responder <pisa.responder.Responder>`): a ``Responder`` instance.


    Attributes:
        appointments (:obj:`dict`): a dictionary containing a simplification of the appointments (:obj:`Appointment
            <pisa.appointment.Appointment>` instances) accepted by the tower (``locator`` and ``end_time``).
            It's populated trough ``add_appointment``.
        locator_uuid_map (:obj:`dict`): a ``locator:uuid`` map used to allow the :obj:`Watcher` to deal with several
            appointments with the same ``locator``.
        block_queue (:obj:`Queue`): A queue used by the :obj:`Watcher` to receive block hashes from ``bitcoind``. It is
        populated by the :obj:`ChainMonitor <pisa.chain_monitor.ChainMonitor>`.
        config (:obj:`dict`): a dictionary containing all the configuration parameters. Used locally to retrieve
            ``MAX_APPOINTMENTS``  and ``EXPIRY_DELTA``.
        db_manager (:obj:`DBManager <pisa.db_manager>`): A db manager instance to interact with the database.
        signing_key (:mod:`PrivateKey`): a private key used to sign accepted appointments.

    Raises:
        ValueError: if `pisa_sk_file` is not found.

    """

    def __init__(self, db_manager, responder, sk_der, config):
        self.appointments = dict()
        self.locator_uuid_map = dict()
        self.block_queue = Queue()
        self.config = config
        self.db_manager = db_manager
        self.responder = responder
        self.signing_key = Cryptographer.load_private_key_der(sk_der)

    def awake(self):
        watcher_thread = Thread(target=self.do_watch, daemon=True)
        watcher_thread.start()

        return watcher_thread

    def add_appointment(self, appointment):
        """
        Adds a new appointment to the ``appointments`` dictionary if ``max_appointments`` has not been reached.

        ``add_appointment`` is the entry point of the Watcher. Upon receiving a new appointment it will start monitoring
        the blockchain (``do_watch``) until ``appointments`` is empty.

        Once a breach is seen on the blockchain, the :obj:`Watcher` will decrypt the corresponding
        :obj:`EncryptedBlob <common.encrypted_blob.EncryptedBlob>` and pass the information to the
        :obj:`Responder <pisa.responder.Responder>`.

        The tower may store multiple appointments with the same ``locator`` to avoid DoS attacks based on data
        rewriting. `locators`` should be derived from the ``dispute_txid``, but that task is performed by the user, and
        the tower has no way of verifying whether or not they have been properly derived. Therefore, appointments are
        identified by ``uuid`` and stored in ``appointments`` and ``locator_uuid_map``.

        Args:
            appointment (:obj:`Appointment <pisa.appointment.Appointment>`): the appointment to be added to the
                :obj:`Watcher`.

        Returns:
            :obj:`tuple`: A tuple signaling if the appointment has been added or not (based on ``max_appointments``).
            The structure looks as follows:

            - ``(True, signature)`` if the appointment has been accepted.
            - ``(False, None)`` otherwise.

        """

        if len(self.appointments) < self.config.get("MAX_APPOINTMENTS"):

            uuid = uuid4().hex
            self.appointments[uuid] = {"locator": appointment.locator, "end_time": appointment.end_time}

            if appointment.locator in self.locator_uuid_map:
                self.locator_uuid_map[appointment.locator].append(uuid)

            else:
                self.locator_uuid_map[appointment.locator] = [uuid]

            self.db_manager.store_watcher_appointment(uuid, appointment.to_json())
            self.db_manager.create_append_locator_map(appointment.locator, uuid)

            appointment_added = True
            signature = Cryptographer.sign(appointment.serialize(), self.signing_key)

            logger.info("New appointment accepted", locator=appointment.locator)

        else:
            appointment_added = False
            signature = None

            logger.info("Maximum appointments reached, appointment rejected", locator=appointment.locator)

        return appointment_added, signature

    def do_watch(self):
        """
        Monitors the blockchain whilst there are pending appointments.

        This is the main method of the :obj:`Watcher` and the one in charge to pass appointments to the
        :obj:`Responder <pisa.responder.Responder>` upon detecting a breach.
        """

        while True:
            block_hash = self.block_queue.get()
            block = BlockProcessor.get_block(block_hash)
            logger.info("New block received", block_hash=block_hash, prev_block_hash=block.get("previousblockhash"))

            if len(self.appointments) > 0 and block is not None:
                txids = block.get("tx")

                expired_appointments = [
                    uuid
                    for uuid, appointment_data in self.appointments.items()
                    if block["height"] > appointment_data.get("end_time") + self.config.get("EXPIRY_DELTA")
                ]

                Cleaner.delete_expired_appointments(
                    expired_appointments, self.appointments, self.locator_uuid_map, self.db_manager
                )

                valid_breaches, invalid_breaches = self.filter_valid_breaches(self.get_breaches(txids))

                triggered_flags = []
                appointments_to_delete = []

                for uuid, breach in valid_breaches.items():
                    logger.info(
                        "Notifying responder and deleting appointment",
                        penalty_txid=breach["penalty_txid"],
                        locator=breach["locator"],
                        uuid=uuid,
                    )

                    receipt = self.responder.handle_breach(
                        uuid,
                        breach["locator"],
                        breach["dispute_txid"],
                        breach["penalty_txid"],
                        breach["penalty_rawtx"],
                        self.appointments[uuid].get("end_time"),
                        block_hash,
                    )

                    # FIXME: Only necessary because of the triggered appointment approach. Fix if it changes.

                    if receipt.delivered:
                        Cleaner.delete_appointment_from_memory(uuid, self.appointments, self.locator_uuid_map)
                        triggered_flags.append(uuid)
                    else:
                        appointments_to_delete.append(uuid)

                # Appointments are only flagged as triggered if they are delivered, otherwise they are just deleted.
                appointments_to_delete.extend(invalid_breaches)
                self.db_manager.batch_create_triggered_appointment_flag(triggered_flags)

                Cleaner.delete_completed_appointments(
                    appointments_to_delete, self.appointments, self.locator_uuid_map, self.db_manager
                )

                if len(self.appointments) is 0:
                    logger.info("No more pending appointments")

            # Register the last processed block for the watcher
            self.db_manager.store_last_block_hash_watcher(block_hash)
            self.block_queue.task_done()

    def get_breaches(self, txids):
        """
        Gets a list of channel breaches given the list of transaction ids.

        Args:
            txids (:obj:`list`): the list of transaction ids included in the last received block.

        Returns:
            :obj:`dict`: A dictionary (``locator:txid``) with all the breaches found. An empty dictionary if none are
            found.
        """

        potential_locators = {compute_locator(txid): txid for txid in txids}

        # Check is any of the tx_ids in the received block is an actual match
        intersection = set(self.locator_uuid_map.keys()).intersection(potential_locators.keys())
        breaches = {locator: potential_locators[locator] for locator in intersection}

        if len(breaches) > 0:
            logger.info("List of breaches", breaches=breaches)

        else:
            logger.info("No breaches found")

        return breaches

    def filter_valid_breaches(self, breaches):
        """
        Filters what of the found breaches contain valid transaction data.

        The :obj:`Watcher` cannot if a given :obj:`EncryptedBlob <common.encrypted_blob.EncryptedBlob>` contains a valid
        transaction until a breach if seen. Blobs that contain arbitrary data are dropped and not sent to the
        :obj:`Responder <pisa.responder.Responder>`.

        Args:
            breaches (:obj:`dict`): a dictionary containing channel breaches (``locator:txid``).

        Returns:
            :obj:`dict`: A dictionary containing all the breaches flagged either as valid or invalid.
            The structure is as follows:

            ``{locator, dispute_txid, penalty_txid, penalty_rawtx, valid_breach}``
        """

        valid_breaches = {}
        invalid_breaches = []

        # A cache of the already decrypted blobs so replicate decryption can be avoided
        decrypted_blobs = {}

        for locator, dispute_txid in breaches.items():
            for uuid in self.locator_uuid_map[locator]:
                appointment = Appointment.from_dict(self.db_manager.load_watcher_appointment(uuid))

                if appointment.encrypted_blob.data in decrypted_blobs:
                    penalty_tx, penalty_rawtx = decrypted_blobs[appointment.encrypted_blob.data]

                else:
                    try:
                        penalty_rawtx = Cryptographer.decrypt(appointment.encrypted_blob, dispute_txid)

                    except ValueError:
                        penalty_rawtx = None

                    penalty_tx = BlockProcessor.decode_raw_transaction(penalty_rawtx)
                    decrypted_blobs[appointment.encrypted_blob.data] = (penalty_tx, penalty_rawtx)

                if penalty_tx is not None:
                    valid_breaches[uuid] = {
                        "locator": locator,
                        "dispute_txid": dispute_txid,
                        "penalty_txid": penalty_tx.get("txid"),
                        "penalty_rawtx": penalty_rawtx,
                    }

                    logger.info(
                        "Breach found for locator", locator=locator, uuid=uuid, penalty_txid=penalty_tx.get("txid")
                    )

                else:
                    invalid_breaches.append(uuid)

        return valid_breaches, invalid_breaches
