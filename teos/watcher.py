from queue import Queue
from threading import Thread

from common.logger import Logger
from common.tools import compute_locator
from common.exceptions import BasicException
from common.exceptions import EncryptionError
from common.cryptographer import Cryptographer, hash_160
from common.exceptions import InvalidParameter, SignatureError

from teos import LOG_PREFIX
from teos.cleaner import Cleaner
from teos.extended_appointment import ExtendedAppointment

logger = Logger(actor="Watcher", log_name_prefix=LOG_PREFIX)


class AppointmentLimitReached(BasicException):
    """Raised when the tower maximum appointment count has been reached"""


class Watcher:
    """
    The :class:`Watcher` is in charge of watching for channel breaches for the appointments accepted by the tower.

    The :class:`Watcher` keeps track of the accepted appointments in ``appointments`` and, for new received block,
    checks if any breach has happened by comparing the txids with the appointment locators. If a breach is seen, the
    ``encrypted_blob`` of the corresponding appointment is decrypted and the data is passed to the
    :obj:`Responder <teos.responder.Responder>`.

    If an appointment reaches its end with no breach, the data is simply deleted.

    The :class:`Watcher` receives information about new received blocks via the ``block_queue`` that is populated by the
    :obj:`ChainMonitor <teos.chain_monitor.ChainMonitor>`.

    Args:
        db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): a ``AppointmentsDBM`` instance
            to interact with the database.
        block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): a ``BlockProcessor`` instance to
            get block from bitcoind.
        responder (:obj:`Responder <teos.responder.Responder>`): a ``Responder`` instance.
        sk_der (:obj:`bytes`): a DER encoded private key used to sign appointment receipts (signaling acceptance).
        max_appointments (:obj:`int`): the maximum amount of appointments accepted by the ``Watcher`` at the same time.

    Attributes:
        appointments (:obj:`dict`): a dictionary containing a summary of the appointments (:obj:`ExtendedAppointment
            <teos.extended_appointment.ExtendedAppointment>` instances) accepted by the tower (``locator``,
            ``user_id``, and ``size``). It's populated trough ``add_appointment``.
        locator_uuid_map (:obj:`dict`): a ``locator:uuid`` map used to allow the :obj:`Watcher` to deal with several
            appointments with the same ``locator``.
        block_queue (:obj:`Queue`): A queue used by the :obj:`Watcher` to receive block hashes from ``bitcoind``. It is
        populated by the :obj:`ChainMonitor <teos.chain_monitor.ChainMonitor>`.
        db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): a ``AppointmentsDBM`` instance
            to interact with the database.
        gatekeeper (:obj:`Gatekeeper <teos.gatekeeper.Gatekeeper>`): a `Gatekeeper` instance in charge to control the
            user access and subscription expiry.
        block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): a ``BlockProcessor`` instance to
            get block from bitcoind.
        responder (:obj:`Responder <teos.responder.Responder>`): a ``Responder`` instance.
        signing_key (:mod:`PrivateKey`): a private key used to sign accepted appointments.
        max_appointments (:obj:`int`): the maximum amount of appointments accepted by the ``Watcher`` at the same time.
        expiry_delta (:obj:`int`): the additional time the ``Watcher`` will keep an expired appointment around.
        last_known_block (:obj:`str`): the last block known by the ``Watcher``.

    Raises:
        :obj:`InvalidKey <common.exceptions.InvalidKey>`: if teos sk cannot be loaded.

    """

    def __init__(self, db_manager, gatekeeper, block_processor, responder, sk_der, max_appointments):
        self.appointments = dict()
        self.locator_uuid_map = dict()
        self.block_queue = Queue()
        self.db_manager = db_manager
        self.gatekeeper = gatekeeper
        self.block_processor = block_processor
        self.responder = responder
        self.max_appointments = max_appointments
        self.signing_key = Cryptographer.load_private_key_der(sk_der)
        self.last_known_block = db_manager.load_last_block_hash_watcher()

    def awake(self):
        """Starts a new thread to monitor the blockchain for channel breaches"""

        watcher_thread = Thread(target=self.do_watch, daemon=True)
        watcher_thread.start()

        return watcher_thread

    def add_appointment(self, appointment, signature):
        """
        Adds a new appointment to the ``appointments`` dictionary if ``max_appointments`` has not been reached.

        ``add_appointment`` is the entry point of the ``Watcher``. Upon receiving a new appointment it will start
        monitoring the blockchain (``do_watch``) until ``appointments`` is empty.

        Once a breach is seen on the blockchain, the :obj:`Watcher` will decrypt the corresponding ``encrypted_blob``
        and pass the information to the :obj:`Responder <teos.responder.Responder>`.

        The tower may store multiple appointments with the same ``locator`` to avoid DoS attacks based on data
        rewriting. `locators`` should be derived from the ``dispute_txid``, but that task is performed by the user, and
        the tower has no way of verifying whether or not they have been properly derived. Therefore, appointments are
        identified by ``uuid`` and stored in ``appointments`` and ``locator_uuid_map``.

        Args:
            appointment (:obj:`ExtendedAppointment <teos.extended_appointment.ExtendedAppointment>`): the appointment to
                be added to the :obj:`Watcher`.
            signature (:obj:`str`): the user's appointment signature (hex-encoded).

        Returns:
            :obj:`dict`: The tower response as a dict, containing: locator, signature, available_slots and
            subscription_expiry.

        Raises:
            :obj:`AppointmentLimitReached`: If the tower cannot hold more appointments (cap reached).
            :obj:`AuthenticationFailure <teos.gatekeeper.AuthenticationFailure>`: If the user cannot be authenticated.
            :obj:`NotEnoughSlots <teos.gatekeeper.NotEnoughSlots>`: If the user does not have enough available slots,
            so the appointment is rejected
        """

        if len(self.appointments) >= self.max_appointments:
            message = "Maximum appointments reached, appointment rejected"
            logger.info(message, locator=appointment.locator)
            raise AppointmentLimitReached(message)

        user_id = self.gatekeeper.authenticate_user(appointment.serialize(), signature)

        # The uuids are generated as the RIPMED160(locator||user_pubkey).
        # If an appointment is requested by the user the uuid can be recomputed and queried straightaway (no maps).
        uuid = hash_160("{}{}".format(appointment.locator, user_id))
        appointment_dict = {"locator": appointment.locator, "user_id": user_id, "size": len(appointment.encrypted_blob)}

        available_slots = self.gatekeeper.update_available_slots(user_id, appointment_dict, self.appointments.get(uuid))
        self.gatekeeper.registered_users[user_id].appointments.append(uuid)
        self.appointments[uuid] = appointment_dict

        if appointment.locator in self.locator_uuid_map:
            # If the uuid is already in the map it means this is an update.
            if uuid not in self.locator_uuid_map[appointment.locator]:
                self.locator_uuid_map[appointment.locator].append(uuid)
        else:
            self.locator_uuid_map[appointment.locator] = [uuid]

        self.db_manager.store_watcher_appointment(uuid, appointment.to_dict())
        self.db_manager.create_append_locator_map(appointment.locator, uuid)

        try:
            signature = Cryptographer.sign(appointment.serialize(), self.signing_key)

        except (InvalidParameter, SignatureError):
            # This should never happen since data is sanitized, just in case to avoid a crash
            logger.error("Data couldn't be signed", appointment=appointment.to_dict())
            signature = None

        logger.info("New appointment accepted", locator=appointment.locator)

        return {
            "locator": appointment.locator,
            "signature": signature,
            "available_slots": available_slots,
            "subscription_expiry": self.gatekeeper.registered_users[user_id].subscription_expiry,
        }

    def do_watch(self):
        """
        Monitors the blockchain for channel breaches.

        This is the main method of the :obj:`Watcher` and the one in charge to pass appointments to the
        :obj:`Responder <teos.responder.Responder>` upon detecting a breach.
        """

        # Distinguish fresh bootstraps from bootstraps from db
        if self.last_known_block is None:
            self.last_known_block = self.block_processor.get_best_block_hash()
            self.db_manager.store_last_block_hash_watcher(self.last_known_block)

        while True:
            block_hash = self.block_queue.get()
            block = self.block_processor.get_block(block_hash)
            logger.info("New block received", block_hash=block_hash, prev_block_hash=block.get("previousblockhash"))

            if len(self.appointments) > 0 and block is not None:
                txids = block.get("tx")

                expired_appointments = self.gatekeeper.get_expired_appointments(block["height"])
                # Make sure we only try to delete what is on the Watcher (some appointments may have been triggered)
                expired_appointments = list(set(expired_appointments).intersection(self.appointments.keys()))

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
                        self.appointments[uuid].get("user_id"),
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

                if len(self.appointments) != 0:
                    logger.info("No more pending appointments")

            # Register the last processed block for the watcher
            self.db_manager.store_last_block_hash_watcher(block_hash)
            self.last_known_block = block.get("hash")
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

        The :obj:`Watcher` cannot if a given ``encrypted_blob`` contains a valid transaction until a breach if seen.
        Blobs that contain arbitrary data are dropped and not sent to the :obj:`Responder <teos.responder.Responder>`.

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
                appointment = ExtendedAppointment.from_dict(self.db_manager.load_watcher_appointment(uuid))

                if appointment.encrypted_blob in decrypted_blobs:
                    penalty_tx, penalty_rawtx = decrypted_blobs[appointment.encrypted_blob]

                else:
                    try:
                        penalty_rawtx = Cryptographer.decrypt(appointment.encrypted_blob, dispute_txid)

                    except EncryptionError:
                        penalty_rawtx = None

                    penalty_tx = self.block_processor.decode_raw_transaction(penalty_rawtx)
                    decrypted_blobs[appointment.encrypted_blob] = (penalty_tx, penalty_rawtx)

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
