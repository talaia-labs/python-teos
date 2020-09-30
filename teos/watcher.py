from queue import Queue
from threading import Thread
from collections import OrderedDict
from readerwriterlock import rwlock

from teos.logger import get_logger
import common.receipts as receipts
from common.appointment import AppointmentStatus
from common.tools import compute_locator
from common.exceptions import BasicException, EncryptionError, InvalidParameter, SignatureError
from common.cryptographer import Cryptographer, hash_160

from teos.cleaner import Cleaner
from teos.chain_monitor import ChainMonitor
from teos.gatekeeper import SubscriptionExpired
from teos.extended_appointment import ExtendedAppointment
from teos.block_processor import InvalidTransactionFormat


class AppointmentLimitReached(BasicException):
    """Raised when the tower maximum appointment count has been reached."""


class AppointmentAlreadyTriggered(BasicException):
    """
    Raised when an appointment is sent to the Watcher but that same data has already been sent to the :obj:`Responder`.
    """


class AppointmentNotFound(BasicException):
    """Raised when an appointment is not found on the tower."""


class LocatorCache:
    """
    The :obj:`LocatorCache` keeps the data about the last ``cache_size`` blocks around so appointments can be checked
    against it. The data is indexed by locator and it's mainly built during the normal :obj:`Watcher` operation so no
    extra steps are normally needed.

    Args:
        blocks_in_cache (:obj:`int`): the numbers of blocks to keep in the cache.

    Attributes:
        logger (:obj:`Logger <teos.logger.Logger>`): The logger for this component.
        cache (:obj:`dict`): A dictionary of ``locator:dispute_txid`` pairs that received appointments are checked
            against.
        blocks (:obj:`OrderedDict`): An ordered dictionary of the last ``blocks_in_cache`` blocks
            (``block_hash:locators``). Used to keep track of what data belongs to what block, so data can be pruned
            accordingly. Also needed to rebuild the cache in case of reorgs.
        cache_size (:obj:`int`): The size of the cache in blocks.
    """

    def __init__(self, blocks_in_cache):
        self.logger = get_logger(component=LocatorCache.__name__)
        self.cache = dict()
        self.blocks = OrderedDict()
        self.cache_size = blocks_in_cache
        self.rw_lock = rwlock.RWLockWrite()

    def init(self, last_known_block, block_processor):
        """
        Sets the initial state of the locator cache.

        Args:
            last_known_block (:obj:`str`): the last known block by the :obj:`Watcher`.
            block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): a block processor instance.
        """

        # This is needed as a separate method from __init__ since it has to be initialized right before start watching.
        # Not doing so implies store temporary variables in the Watcher and initialising the cache as None.
        target_block_hash = last_known_block
        for _ in range(self.cache_size):
            # In some setups, like regtest, it could be the case that there are no enough previous blocks.
            # In those cases we pull as many as we can (up to cache_size).
            if not target_block_hash:
                break

            target_block = block_processor.get_block(target_block_hash)
            if not target_block:
                break

            locator_txid_map = {compute_locator(txid): txid for txid in target_block.get("tx")}
            self.cache.update(locator_txid_map)
            self.blocks[target_block_hash] = list(locator_txid_map.keys())
            target_block_hash = target_block.get("previousblockhash")

        self.blocks = OrderedDict(reversed((list(self.blocks.items()))))

    def get_txid(self, locator):
        """
        Gets a txid from the locator cache.

        Args:
            locator (:obj:`str`): the locator to lookup in the cache.

        Returns:
            :obj:`str` or :obj:`None`: The txid linked to the given locator if found. None otherwise.
        """

        with self.rw_lock.gen_rlock():
            locator = self.cache.get(locator)
        return locator

    def update(self, block_hash, locator_txid_map):
        """
        Updates the cache with data from a new block. Removes the oldest block if the cache is full after the addition.

        Args:
            block_hash (:obj:`str`): the hash of the new block.
            locator_txid_map (:obj:`dict`): the dictionary of locators (locator:txid) derived from a list of transaction
                ids.
        """

        with self.rw_lock.gen_wlock():
            self.cache.update(locator_txid_map)
            self.blocks[block_hash] = list(locator_txid_map.keys())
            self.logger.debug("Block added to cache", block_hash=block_hash)

        if self.is_full():
            self.remove_oldest_block()

    def is_full(self):
        """  Returns whether the cache is full or not."""
        with self.rw_lock.gen_rlock():
            full = len(self.blocks) > self.cache_size
        return full

    def remove_oldest_block(self):
        """ Removes the oldest block from the cache."""
        with self.rw_lock.gen_wlock():
            block_hash, locators = self.blocks.popitem(last=False)
            for locator in locators:
                del self.cache[locator]

        self.logger.debug("Block removed from cache", block_hash=block_hash)

    def fix(self, last_known_block, block_processor):
        """
        Fixes the cache after a reorg has been detected by feeding the most recent ``cache_size`` blocks to it.

        Args:
            last_known_block (:obj:`str`): the last known block hash after the reorg.
            block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): a block processor instance.
        """

        tmp_cache = LocatorCache(self.cache_size)

        # We assume there are no reorgs back to genesis. If so, this would raise some log warnings. And the cache will
        # be filled with less than cache_size blocks.
        target_block_hash = last_known_block
        for _ in range(tmp_cache.cache_size):
            target_block = block_processor.get_block(target_block_hash)
            if target_block:
                # Compute the locator:txid pair for every transaction in the block and update both the cache and
                # the block mapping.
                locator_txid_map = {compute_locator(txid): txid for txid in target_block.get("tx")}
                tmp_cache.cache.update(locator_txid_map)
                tmp_cache.blocks[target_block_hash] = list(locator_txid_map.keys())
                target_block_hash = target_block.get("previousblockhash")

        with self.rw_lock.gen_wlock():
            self.blocks = OrderedDict(reversed((list(tmp_cache.blocks.items()))))
            self.cache = tmp_cache.cache


class Watcher:
    """
    The :class:`Watcher` is in charge of watching for channel breaches for the appointments accepted by the tower.

    The :class:`Watcher` keeps track of the accepted appointments in ``appointments`` and, for new received blocks,
    checks if any breach has happened by comparing the txids with the appointment locators. If a breach is seen, the
    ``encrypted_blob`` of the corresponding appointment is decrypted and the data is passed to the
    :obj:`Responder <teos.responder.Responder>`.

    If an appointment reaches its end with no breach, the data is simply deleted.

    The :class:`Watcher` receives information about new received blocks via the ``block_queue`` that is populated by the
    :obj:`ChainMonitor <teos.chain_monitor.ChainMonitor>`.

    Args:
        db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): an instance of the appointment
                database manager to interact with the database.
        block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): a block processor instance to
            get block from bitcoind.
        responder (:obj:`Responder <teos.responder.Responder>`): a responder instance.
        sk (:obj:`PrivateKey`): a private key used to sign accepted appointments.
        max_appointments (:obj:`int`): the maximum amount of appointments accepted by the :obj:`Watcher` at the same
            time.
        blocks_in_cache (:obj:`int`): the number of blocks to keep in cache so recently triggered appointments can be
            covered.

    Attributes:
        appointments (:obj:`dict`): A dictionary containing a summary of the appointments (:obj:`ExtendedAppointment
            <teos.extended_appointment.ExtendedAppointment>` instances) accepted by the tower (``locator`` and
            ``user_id``). It's populated trough ``add_appointment``.
        locator_uuid_map (:obj:`dict`): A ``locator:uuid`` map used to allow the :obj:`Watcher` to deal with several
            appointments with the same ``locator``.
        block_queue (:obj:`Queue`): A queue used by the :obj:`Watcher` to receive block hashes from ``bitcoind``. It is
            populated by the :obj:`ChainMonitor <teos.chain_monitor.ChainMonitor>`.
        db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): An instance of the appointment
                database manager to interact with the database.
        gatekeeper (:obj:`Gatekeeper <teos.gatekeeper.Gatekeeper>`): A gatekeeper instance in charge to control the
            user access and subscription expiry.
        block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): A block processor instance to
            get block from bitcoind.
        responder (:obj:`Responder <teos.responder.Responder>`): A responder instance.
        signing_key (:obj:`PrivateKey`): A private key used to sign accepted appointments.
        max_appointments (:obj:`int`): The maximum amount of appointments accepted by the :obj:`Watcher` at the same
            time.
        last_known_block (:obj:`str`): The last block known by the :obj:`Watcher`.
        locator_cache (:obj:`LocatorCache`): A cache of locators for the last ``blocks_in_cache`` blocks.

    Raises:
        :obj:`InvalidKey`: if teos sk cannot be loaded.
    """

    def __init__(self, db_manager, gatekeeper, block_processor, responder, sk, max_appointments, blocks_in_cache):
        self.logger = get_logger(component=Watcher.__name__)

        self.appointments = dict()
        self.locator_uuid_map = dict()
        self.block_queue = Queue()
        self.db_manager = db_manager
        self.gatekeeper = gatekeeper
        self.block_processor = block_processor
        self.responder = responder
        self.max_appointments = max_appointments
        self.signing_key = sk
        self.last_known_block = db_manager.load_last_block_hash_watcher()
        self.locator_cache = LocatorCache(blocks_in_cache)

    @property
    def tower_id(self):
        """Get the id of this tower, as a hex string."""
        return Cryptographer.get_compressed_pk(self.signing_key.public_key)

    @property
    def n_registered_users(self):
        """Get the number of users currently registered to the tower."""
        return len(self.gatekeeper.registered_users)

    @property
    def n_watcher_appointments(self):
        """Get the total number of appointments stored in the watcher."""
        return len(self.appointments)

    @property
    def n_responder_trackers(self):
        """Get the total number of trackers in the responder."""
        return len(self.responder.trackers)

    def awake(self):
        """
        Starts a new thread to monitor the blockchain for channel breaches. The thread will run until the
        :obj:`ChainMonitor` adds ``ChainMonitor.END_MESSAGE`` to the queue.

        Returns:
            :obj:`Thread <multithreading.Thread>`: The thread object that was just created and is already running.
        """

        watcher_thread = Thread(target=self.do_watch, daemon=True)
        watcher_thread.start()
        return watcher_thread

    def register(self, user_id):
        """
        Registers a user.

        Args:
            user_id (:obj:`str`): the public key that identifies the user (33-bytes hex str).

        Returns:
            :obj:`tuple`: A tuple containing the available slots, the subscription expiry, and the signature of the
            registration receipt by the Watcher.
        """

        available_slots, subscription_expiry, registration_receipt = self.gatekeeper.add_update_user(user_id)
        signature = Cryptographer.sign(registration_receipt, self.signing_key)

        return available_slots, subscription_expiry, signature

    def get_appointment(self, locator, user_signature):
        """
        Gets information about an appointment.

        The appointment can either be in the watcher, the responder, or not found.

        Args:
            locator (:obj:`str`): a 16-byte hex-encoded value used by the tower to detect channel breaches.
            user_signature (:obj:`str`): the signature of the request by the user.

        Returns:
            :obj:`tuple`: A tuple containing the appointment data and the status, either
                ``AppointmentStatus.BEING_WATCHED`` or ``AppointmentStatus.DISPUTE_RESPONDED``

        Raises:
            :obj:`AppointmentNotFound`: if the appointment is not found in the tower.
            :obj:`SubscriptionExpired`: If the user subscription has expired.
        """

        message = "get appointment {}".format(locator).encode("utf-8")
        user_id = self.gatekeeper.authenticate_user(message, user_signature)
        if self.gatekeeper.has_subscription_expired(user_id):
            raise SubscriptionExpired(
                f"Your subscription expired at block {self.gatekeeper.registered_users[user_id].subscription_expiry}"
            )
        uuid = hash_160("{}{}".format(locator, user_id))

        if uuid in self.appointments:
            appointment_data = self.db_manager.load_watcher_appointment(uuid)
            status = AppointmentStatus.BEING_WATCHED
        elif uuid in self.responder.trackers:
            appointment_data = self.db_manager.load_responder_tracker(uuid)
            status = AppointmentStatus.DISPUTE_RESPONDED
        else:
            raise AppointmentNotFound("Cannot find {}".format(locator))

        return appointment_data, status

    def add_appointment(self, appointment, user_signature):
        """
        Adds a new appointment to the ``appointments`` dictionary if ``max_appointments`` has not been reached.

        ``add_appointment`` is the entry point of the :obj:`Watcher`. Upon receiving a new appointment it will start
        monitoring the blockchain (``do_watch``) until ``appointments`` is empty.

        Once a breach is seen on the blockchain, the :obj:`Watcher` will decrypt the corresponding ``encrypted_blob``
        and pass the information to the :obj:`Responder <teos.responder.Responder>`.

        The tower may store multiple appointments with the same ``locator`` to avoid DoS attacks based on data
        rewriting. `locators`` should be derived from the ``dispute_txid``, but that task is performed by the user, and
        the tower has no way of verifying whether or not they have been properly derived. Therefore, appointments are
        identified by ``uuid`` and stored in ``appointments`` and ``locator_uuid_map``.

        Args:
            appointment (:obj:`Appointment <common.appointment.Appointment>`): the appointment to be added to the
                :obj:`Watcher`.
            user_signature (:obj:`str`): the user's appointment signature (hex-encoded).

        Returns:
            :obj:`dict`: The tower response as a dict, containing: ``locator``, ``signature``, ``available_slots`` and
            ``subscription_expiry``.

        Raises:
            :obj:`AppointmentLimitReached`: If the tower cannot hold more appointments (cap reached).
            :obj:`AuthenticationFailure`: If the user cannot be authenticated.
            :obj:`NotEnoughSlots`: If the user does not have enough available slots, so the appointment is rejected.\
            :obj:`SubscriptionExpired`: If the user subscription has expired.
        """

        if len(self.appointments) >= self.max_appointments:
            message = "Maximum appointments reached, appointment rejected"
            self.logger.info(message, locator=appointment.locator)
            raise AppointmentLimitReached(message)

        user_id = self.gatekeeper.authenticate_user(appointment.serialize(), user_signature)
        if self.gatekeeper.has_subscription_expired(user_id):
            raise SubscriptionExpired(
                f"Your subscription expired at block {self.gatekeeper.registered_users[user_id].subscription_expiry}"
            )
        start_block = self.block_processor.get_block(self.last_known_block).get("height")
        extended_appointment = ExtendedAppointment(
            appointment.locator,
            appointment.encrypted_blob,
            appointment.to_self_delay,
            user_id,
            user_signature,
            start_block,
        )

        # The uuids are generated as the RIPEMD160(locator||user_pubkey).
        # If an appointment is requested by the user the uuid can be recomputed and queried straightaway (no maps).
        uuid = hash_160("{}{}".format(extended_appointment.locator, user_id))

        # If this is a copy of an appointment we've already reacted to, the new appointment is rejected.
        if uuid in self.responder.trackers:
            message = "Appointment already in Responder"
            self.logger.info(message)
            raise AppointmentAlreadyTriggered(message)

        # Add the appointment to the Gatekeeper
        available_slots = self.gatekeeper.add_update_appointment(user_id, uuid, extended_appointment)

        # Appointments that were triggered in blocks held in the cache
        dispute_txid = self.locator_cache.get_txid(extended_appointment.locator)
        if dispute_txid:
            try:
                penalty_txid, penalty_rawtx = self.check_breach(uuid, extended_appointment, dispute_txid)
                receipt = self.responder.handle_breach(
                    uuid,
                    extended_appointment.locator,
                    dispute_txid,
                    penalty_txid,
                    penalty_rawtx,
                    user_id,
                    self.last_known_block,
                )

                # At this point the appointment is accepted but data is only kept if it goes through the Responder.
                # Otherwise it is dropped.
                if receipt.delivered:
                    self.db_manager.store_watcher_appointment(uuid, extended_appointment.to_dict())
                    self.db_manager.create_append_locator_map(extended_appointment.locator, uuid)
                    self.db_manager.create_triggered_appointment_flag(uuid)

            except (EncryptionError, InvalidTransactionFormat):
                # If data inside the encrypted blob is invalid, the appointment is accepted but the data is dropped.
                # (same as with data that bounces in the Responder). This reduces the appointment slot count so it
                # could be used to discourage user misbehaviour.
                pass

        # Regular appointments that have not been triggered (or, at least, not recently)
        else:
            self.appointments[uuid] = extended_appointment.get_summary()

            if extended_appointment.locator in self.locator_uuid_map:
                # If the uuid is already in the map it means this is an update.
                if uuid not in self.locator_uuid_map[extended_appointment.locator]:
                    self.locator_uuid_map[extended_appointment.locator].append(uuid)
            else:
                # Otherwise two users have sent an appointment with the same locator, so we need to store both.
                self.locator_uuid_map[extended_appointment.locator] = [uuid]

            self.db_manager.store_watcher_appointment(uuid, extended_appointment.to_dict())
            self.db_manager.create_append_locator_map(extended_appointment.locator, uuid)

        try:
            signature = Cryptographer.sign(
                receipts.create_appointment_receipt(user_signature, start_block), self.signing_key
            )

        except (InvalidParameter, SignatureError):
            # This should never happen since data is sanitized, just in case to avoid a crash
            self.logger.error("Data couldn't be signed", appointment=extended_appointment.to_dict())
            signature = None

        self.logger.info("New appointment accepted", locator=extended_appointment.locator)

        return {
            "locator": extended_appointment.locator,
            "start_block": extended_appointment.start_block,
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

        # Initialise the locator cache with the last ``cache_size`` blocks.
        self.locator_cache.init(self.last_known_block, self.block_processor)

        while True:
            block_hash = self.block_queue.get()

            # When the ChainMonitor is stopped, a final ChainMonitor.END_MESSAGE message is sent
            if block_hash == ChainMonitor.END_MESSAGE:
                break

            block = self.block_processor.get_block(block_hash)
            self.logger.info(
                "New block received", block_hash=block_hash, prev_block_hash=block.get("previousblockhash")
            )

            # If a reorg is detected, the cache is fixed to cover the last `cache_size` blocks of the new chain
            if self.last_known_block != block.get("previousblockhash"):
                self.locator_cache.fix(block_hash, self.block_processor)

            txids = block.get("tx")
            # Compute the locator for every transaction in the block and add them to the cache
            locator_txid_map = {compute_locator(txid): txid for txid in txids}
            self.locator_cache.update(block_hash, locator_txid_map)

            if len(self.appointments) > 0 and locator_txid_map:
                outdated_appointments = self.gatekeeper.get_outdated_appointments(block["height"])
                # Make sure we only try to delete what is on the Watcher (some appointments may have been triggered)
                outdated_appointments = list(set(outdated_appointments).intersection(self.appointments.keys()))

                Cleaner.delete_outdated_appointments(
                    outdated_appointments, self.appointments, self.locator_uuid_map, self.db_manager
                )

                valid_breaches, invalid_breaches = self.filter_breaches(self.get_breaches(locator_txid_map))

                triggered_flags = []
                appointments_to_delete = []

                for uuid, breach in valid_breaches.items():
                    self.logger.info(
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
                appointments_to_delete_gatekeeper = {
                    uuid: self.appointments[uuid].get("user_id") for uuid in appointments_to_delete
                }
                self.db_manager.batch_create_triggered_appointment_flag(triggered_flags)

                Cleaner.delete_completed_appointments(
                    appointments_to_delete, self.appointments, self.locator_uuid_map, self.db_manager
                )
                # Remove invalid appointments from the Gatekeeper
                with self.gatekeeper.lock:
                    Cleaner.delete_gatekeeper_appointments(
                        appointments_to_delete_gatekeeper, self.gatekeeper.registered_users, self.gatekeeper.user_db
                    )

                if not self.appointments:
                    self.logger.info("No more pending appointments")

            # Register the last processed block for the Watcher
            self.db_manager.store_last_block_hash_watcher(block_hash)
            self.last_known_block = block.get("hash")
            self.block_queue.task_done()

    def get_breaches(self, locator_txid_map):
        """
        Gets a dictionary of channel breaches given a map of ``locator:dispute_txid``.

        Args:
            locator_txid_map (:obj:`dict`): the dictionary of locators (locator:txid) derived from a list of
                transaction ids.

        Returns:
            :obj:`dict`: A dictionary (``locator:txid``) with all the breaches found. An empty dictionary if none are
            found.
        """

        # Check is any of the tx_ids in the received block is an actual match
        intersection = set(self.locator_uuid_map.keys()).intersection(locator_txid_map.keys())
        breaches = {locator: locator_txid_map[locator] for locator in intersection}

        if len(breaches) > 0:
            self.logger.info("List of breaches", breaches=breaches)

        else:
            self.logger.info("No breaches found")

        return breaches

    def check_breach(self, uuid, appointment, dispute_txid):
        """
        Checks if a breach is valid. Valid breaches should decrypt to a valid transaction.

        Args:
            uuid (:obj:`str`): the uuid of the appointment that was triggered by the breach.
            appointment (:obj:`ExtendedAppointment <teos.extended_appointment.ExtendedAppointment>`): the appointment
                data.
            dispute_txid (:obj:`str`): the id of the transaction that triggered the breach.

        Returns:
            :obj:`tuple`: A tuple containing the penalty txid and the raw penalty tx.

        Raises:
            :obj:`EncryptionError`: if the encrypted blob from the provided appointment cannot be decrypted with the
                key derived from the breach transaction id.
            :obj:`InvalidTransactionFormat`: if the decrypted data does not have a valid transaction format.
        """

        try:
            penalty_rawtx = Cryptographer.decrypt(appointment.encrypted_blob, dispute_txid)
            penalty_tx = self.block_processor.decode_raw_transaction(penalty_rawtx)

        except EncryptionError as e:
            self.logger.info("Transaction cannot be decrypted", uuid=uuid)
            raise e

        except InvalidTransactionFormat as e:
            self.logger.info("The breach contained an invalid transaction", uuid=uuid)
            raise e

        self.logger.info(
            "Breach found for locator", locator=appointment.locator, uuid=uuid, penalty_txid=penalty_tx.get("txid")
        )

        return penalty_tx.get("txid"), penalty_rawtx

    def filter_breaches(self, breaches):
        """
        Filters the valid from the invalid channel breaches.

        The :obj:`Watcher` cannot know if an ``encrypted_blob`` contains a valid transaction until a breach is seen.
        Blobs that contain arbitrary data are dropped and not sent to the :obj:`Responder <teos.responder.Responder>`.

        Args:
            breaches (:obj:`dict`): a dictionary containing channel breaches (``locator:txid``).

        Returns:
            :obj:`tuple`: A dictionary and a list. The former contains the valid breaches, while the latter contain the
            invalid ones.

            The valid breaches dictionary has the following structure:

            ``{locator, dispute_txid, penalty_txid, penalty_rawtx}``
        """

        valid_breaches = {}
        invalid_breaches = []

        # A cache of the already decrypted blobs so replicate decryption can be avoided
        decrypted_blobs = {}

        for locator, dispute_txid in breaches.items():
            for uuid in self.locator_uuid_map[locator]:
                appointment = ExtendedAppointment.from_dict(self.db_manager.load_watcher_appointment(uuid))

                if appointment.encrypted_blob in decrypted_blobs:
                    penalty_txid, penalty_rawtx = decrypted_blobs[appointment.encrypted_blob]
                    valid_breaches[uuid] = {
                        "locator": appointment.locator,
                        "dispute_txid": dispute_txid,
                        "penalty_txid": penalty_txid,
                        "penalty_rawtx": penalty_rawtx,
                    }

                else:
                    try:
                        penalty_txid, penalty_rawtx = self.check_breach(uuid, appointment, dispute_txid)
                        valid_breaches[uuid] = {
                            "locator": appointment.locator,
                            "dispute_txid": dispute_txid,
                            "penalty_txid": penalty_txid,
                            "penalty_rawtx": penalty_rawtx,
                        }
                        decrypted_blobs[appointment.encrypted_blob] = (penalty_txid, penalty_rawtx)

                    except (EncryptionError, InvalidTransactionFormat):
                        invalid_breaches.append(uuid)

        return valid_breaches, invalid_breaches

    def get_registered_user_ids(self):
        """Returns the list of user ids of all the registered users."""
        return list(self.gatekeeper.registered_users.keys())

    def get_user_info(self, user_id):
        """
        Returns the data held by the tower about the user given an ``user_id``.

        Args:
            user_id (:obj:`str`): the id of the requested user.

        Returns:
            :obj:`UserInfo <teos.gatekeeper.UserInfo> or :obj:`None`: The user data if found. :obj:`None` if not found, or
            the ``user_id`` is invalid.
        """
        return self.gatekeeper.registered_users.get(user_id)

    def get_all_watcher_appointments(self):
        """Returns a dictionary with all the appointment stored in the db for the watcher."""
        return self.db_manager.load_watcher_appointments()

    def get_all_responder_trackers(self):
        """Returns a dictionary with all the trackers stored in the db for the responder."""
        return self.db_manager.load_responder_trackers()
