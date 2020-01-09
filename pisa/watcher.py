from uuid import uuid4
from queue import Queue
from threading import Thread

from common.cryptographer import Cryptographer
from common.constants import LOCATOR_LEN_HEX
from common.appointment import Appointment
from common.logger import Logger

from pisa.cleaner import Cleaner
from pisa.responder import Responder
from pisa.block_processor import BlockProcessor
from pisa.utils.zmq_subscriber import ZMQSubscriber
from pisa.conf import EXPIRY_DELTA, MAX_APPOINTMENTS

logger = Logger("Watcher")


class Watcher:
    """
    The :class:`Watcher` is the class in charge to watch for channel breaches for the appointments accepted by the
    tower.

    The :class:`Watcher` keeps track of the accepted appointments in ``appointments`` and, for new received block,
    checks if any breach has happened by comparing the txids with the appointment locators. If a breach is seen, the
    :obj:`EncryptedBlob <pisa.encrypted_blob.EncryptedBlob>` of the corresponding appointment is decrypted and the data
    is passed to the :obj:`Responder <pisa.responder.Responder>`.

    If an appointment reaches its end with no breach, the data is simply deleted.

    The :class:`Watcher` receives information about new received blocks via the ``block_queue`` that is populated by the
    :obj:`ZMQSubscriber <pisa.utils.zmq_subscriber>`.

    Args:
        db_manager (:obj:`DBManager <pisa.db_manager>`): a ``DBManager`` instance to interact with the database.
        sk_der (:obj:`bytes`): a DER encoded private key used to sign appointment receipts (signaling acceptance).
        responder (:obj:`Responder <pisa.responder.Responder>`): a ``Responder`` instance. If ``None`` is passed, a new
            instance is created. Populated instances are useful when bootstrapping the system from backed-up data.
        max_appointments(:obj:`int`): the maximum amount of appointments that the :obj:`Watcher` will keep at any given
            time. Defaults to ``MAX_APPOINTMENTS``.


    Attributes:
        appointments (:obj:`dict`): a dictionary containing a simplification of the appointments (:obj:`Appointment
            <pisa.appointment.Appointment>` instances) accepted by the tower (``locator`` and ``end_time``).
            It's populated trough ``add_appointment``.
        locator_uuid_map (:obj:`dict`): a ``locator:uuid`` map used to allow the :obj:`Watcher` to deal with several
            appointments with the same ``locator``.
        asleep (:obj:`bool`): A flag that signals whether the :obj:`Watcher` is asleep or awake.
        block_queue (:obj:`Queue`): A queue used by the :obj:`Watcher` to receive block hashes from ``bitcoind``. It is
            populated by the :obj:`ZMQSubscriber <pisa.utils.zmq_subscriber.ZMQSubscriber>`.
        max_appointments(:obj:`int`): the maximum amount of appointments that the :obj:`Watcher` will keep at any given
            time.
        zmq_subscriber (:obj:`ZMQSubscriber <pisa.utils.zmq_subscriber.ZMQSubscriber>`): a ZMQSubscriber instance used
            to receive new block notifications from ``bitcoind``.
        db_manager (:obj:`DBManager <pisa.db_manager>`): A db manager instance to interact with the database.

    Raises:
        ValueError: if `pisa_sk_file` is not found.

    """

    def __init__(self, db_manager, sk_der, responder=None, max_appointments=MAX_APPOINTMENTS):
        self.appointments = dict()
        self.locator_uuid_map = dict()
        self.asleep = True
        self.block_queue = Queue()
        self.max_appointments = max_appointments
        self.zmq_subscriber = None
        self.db_manager = db_manager
        self.signing_key = Cryptographer.load_private_key_der(sk_der)

        if not isinstance(responder, Responder):
            self.responder = Responder(db_manager)

    @staticmethod
    def compute_locator(tx_id):
        """
        Computes an appointment locator given a transaction id.

        Args:
            tx_id (:obj:`str`): the transaction id used to compute the locator.

        Returns:
           (:obj:`str`): The computed locator.
        """

        return tx_id[:LOCATOR_LEN_HEX]

    def add_appointment(self, appointment):
        """
        Adds a new appointment to the ``appointments`` dictionary if ``max_appointments`` has not been reached.

        ``add_appointment`` is the entry point of the Watcher. Upon receiving a new appointment, if the :obj:`Watcher`
        is asleep, it will be awaken and start monitoring the blockchain (``do_watch``) until ``appointments`` is empty.
        It will go back to sleep once there are no more pending appointments.

        Once a breach is seen on the blockchain, the :obj:`Watcher` will decrypt the corresponding
        :obj:`EncryptedBlob <pisa.encrypted_blob.EncryptedBlob>` and pass the information to the
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

        if len(self.appointments) < self.max_appointments:
            # Appointments are stored in disk, we only keep the end_time, locator and locator_uuid map in memory
            uuid = uuid4().hex
            self.appointments[uuid] = {"locator": appointment.locator, "end_time": appointment.end_time}

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
            signature = Cryptographer.sign(appointment.serialize(), self.signing_key)

            logger.info("New appointment accepted", locator=appointment.locator)

        else:
            appointment_added = False
            signature = None

            logger.info("Maximum appointments reached, appointment rejected", locator=appointment.locator)

        return appointment_added, signature

    def do_subscribe(self):
        """
        Initializes a ``ZMQSubscriber`` instance to listen to new blocks from ``bitcoind``. Block ids are received
        trough the ``block_queue``.
        """

        self.zmq_subscriber = ZMQSubscriber(parent="Watcher")
        self.zmq_subscriber.handle(self.block_queue)

    def do_watch(self):
        """
        Monitors the blockchain whilst there are pending appointments.

        This is the main method of the :obj:`Watcher` and the one in charge to pass appointments to the
        :obj:`Responder <pisa.responder.Responder>` upon detecting a breach.
        """

        while len(self.appointments) > 0:
            block_hash = self.block_queue.get()
            logger.info("New block received", block_hash=block_hash)

            block = BlockProcessor.get_block(block_hash)

            if block is not None:
                txids = block.get("tx")

                logger.info("List of transactions", txids=txids)

                expired_appointments = [
                    uuid
                    for uuid, appointment_data in self.appointments.items()
                    if block["height"] > appointment_data.get("end_time") + EXPIRY_DELTA
                ]

                Cleaner.delete_expired_appointment(
                    expired_appointments, self.appointments, self.locator_uuid_map, self.db_manager
                )

                filtered_breaches = self.filter_valid_breaches(self.get_breaches(txids))

                for uuid, filtered_breach in filtered_breaches.items():
                    # Errors decrypting the Blob will result in a None penalty_txid
                    if filtered_breach["valid_breach"] is True:
                        logger.info(
                            "Notifying responder and deleting appointment",
                            penalty_txid=filtered_breach["penalty_txid"],
                            locator=filtered_breach["locator"],
                            uuid=uuid,
                        )

                        self.responder.handle_breach(
                            uuid,
                            filtered_breach["locator"],
                            filtered_breach["dispute_txid"],
                            filtered_breach["penalty_txid"],
                            filtered_breach["penalty_rawtx"],
                            self.appointments[uuid].get("end_time"),
                            block_hash,
                        )

                    # Delete the appointment and update db
                    Cleaner.delete_completed_appointment(
                        uuid, self.appointments, self.locator_uuid_map, self.db_manager
                    )

                # Register the last processed block for the watcher
                self.db_manager.store_last_block_hash_watcher(block_hash)

        # Go back to sleep if there are no more appointments
        self.asleep = True
        self.zmq_subscriber.terminate = True
        self.block_queue = Queue()

        logger.info("No more pending appointments, going back to sleep")

    def get_breaches(self, txids):
        """
        Gets a list of channel breaches given the list of transaction ids.

        Args:
            txids (:obj:`list`): the list of transaction ids included in the last received block.

        Returns:
            :obj:`dict`: A dictionary (``locator:txid``) with all the breaches found. An empty dictionary if none are
            found.
        """

        potential_locators = {Watcher.compute_locator(txid): txid for txid in txids}

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

        The :obj:`Watcher` cannot if a given :obj:`EncryptedBlob <pisa.encrypted_blob.EncryptedBlob>` contains a valid
        transaction until a breach if seen. Blobs that contain arbitrary data are dropped and not sent to the
        :obj:`Responder <pisa.responder.Responder>`.

        Args:
            breaches (:obj:`dict`): a dictionary containing channel breaches (``locator:txid``).

        Returns:
            :obj:`dict`: A dictionary containing all the breaches flagged either as valid or invalid.
            The structure is as follows:

            ``{locator, dispute_txid, penalty_txid, penalty_rawtx, valid_breach}``
        """

        filtered_breaches = {}

        for locator, dispute_txid in breaches.items():
            for uuid in self.locator_uuid_map[locator]:
                appointment = Appointment.from_dict(self.db_manager.load_watcher_appointment(uuid))

                try:
                    penalty_rawtx = Cryptographer.decrypt(appointment.encrypted_blob, dispute_txid)

                except ValueError:
                    penalty_rawtx = None

                penalty_tx = BlockProcessor.decode_raw_transaction(penalty_rawtx)

                if penalty_tx is not None:
                    penalty_txid = penalty_tx.get("txid")
                    valid_breach = True

                    logger.info("Breach found for locator", locator=locator, uuid=uuid, penalty_txid=penalty_txid)

                else:
                    penalty_txid = None
                    valid_breach = False

                filtered_breaches[uuid] = {
                    "locator": locator,
                    "dispute_txid": dispute_txid,
                    "penalty_txid": penalty_txid,
                    "penalty_rawtx": penalty_rawtx,
                    "valid_breach": valid_breach,
                }

        return filtered_breaches
