from queue import Queue
from threading import Thread
from collections import OrderedDict

from common.logger import Logger
from common.tools import compute_locator
from common.exceptions import BasicException
from common.exceptions import EncryptionError
from common.cryptographer import Cryptographer, hash_160
from common.exceptions import InvalidParameter, SignatureError

from teos import LOG_PREFIX
from teos.cleaner import Cleaner
from teos.extended_appointment import ExtendedAppointment
from teos.block_processor import InvalidTransactionFormat

logger = Logger(actor="Watcher", log_name_prefix=LOG_PREFIX)


class AppointmentLimitReached(BasicException):
    """Raised when the tower maximum appointment count has been reached"""


class AppointmentAlreadyTriggered(BasicException):
    """Raised when an appointment is sent to the Watcher but that same data has already been sent to the Responder"""


class LocatorCache:
    """
    The LocatorCache keeps the data about the last ``cache_size`` blocks around so appointments can be checked against
    it. The data is indexed by locator and it's mainly built during the normal ``Watcher`` operation so no extra steps
    are normally needed.

    Args:
        blocks_in_cache (:obj:`int`): the numbers of blocks to keep in the cache.

    Attributes:
        cache (:obj:`dict`): a dictionary of ``locator:dispute_txid`` pairs that received appointments are checked
            against.
        blocks (:obj:`OrderedDict`): An ordered dictionary of the last ``blocks_in_cache`` blocks (block_hash:locators).
            Used to keep track of what data belongs to what block, so data can be pruned accordingly. Also needed to
            rebuild the cache in case of reorgs.
        cache_size (:obj:`int`): the size of the cache in blocks.
    """

    def __init__(self, blocks_in_cache):
        self.cache = dict()
        self.blocks = OrderedDict()
        self.cache_size = blocks_in_cache

    def init(self, last_known_block, block_processor):
        """
        Sets the initial state of the locator cache.

        Args:
            last_known_block (:obj:`str`): the last known block by the ``Watcher``.
            block_processor (:obj:`teos.block_processor.BlockProcessor`): a ``BlockProcessor`` instance.
        """

        # This is needed as a separate method from __init__ since it has to be initialized right before start watching.
        # Not doing so implies store temporary variables in the Watcher and initialising the cache as None.
        target_block_hash = last_known_block
        for _ in range(self.cache_size):
            # In some setups, like regtest, it could be the case that there are no enough previous blocks.
            # In those cases we pull as many as we can (up to ``cache_size``).
            if target_block_hash:
                target_block = block_processor.get_block(target_block_hash)
                if not target_block:
                    break
            else:
                break

            locator_txid_map = {compute_locator(txid): txid for txid in target_block.get("tx")}
            self.cache.update(locator_txid_map)
            self.blocks[target_block_hash] = list(locator_txid_map.keys())
            target_block_hash = target_block.get("previousblockhash")

        self.blocks = OrderedDict(reversed((list(self.blocks.items()))))

    def fix_cache(self, last_known_block, block_processor):
        tmp_cache = LocatorCache(self.cache_size)

        # We assume there are no reorgs back to genesis. If so, this would raise some log warnings. And the cache will
        # be filled with less than ``cache_size`` blocks.`
        target_block_hash = last_known_block
        for _ in range(tmp_cache.cache_size):
            target_block = block_processor.get_block(target_block_hash)
            if target_block:
                locator_txid_map = {compute_locator(txid): txid for txid in target_block.get("tx")}
                tmp_cache.cache.update(locator_txid_map)
                tmp_cache.blocks[target_block_hash] = list(locator_txid_map.keys())
                target_block_hash = target_block.get("previousblockhash")

        self.blocks = OrderedDict(reversed((list(tmp_cache.blocks.items()))))
        self.cache = tmp_cache.cache

    def is_full(self):
        """  Returns whether the cache is full or not """
        return len(self.blocks) > self.cache_size

    def remove_older_block(self):
        """ Removes the older block from the cache """
        block_hash, locators = self.blocks.popitem(last=False)
        for locator in locators:
            del self.cache[locator]

        logger.debug("Block removed from cache", block_hash=block_hash)


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
        db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): a ``AppointmentsDBM`` instance
            to interact with the database.
        block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): a ``BlockProcessor`` instance to
            get block from bitcoind.
        responder (:obj:`Responder <teos.responder.Responder>`): a ``Responder`` instance.
        sk_der (:obj:`bytes`): a DER encoded private key used to sign appointment receipts (signaling acceptance).
        max_appointments (:obj:`int`): the maximum amount of appointments accepted by the ``Watcher`` at the same time.
        blocks_in_cache (:obj:`int`): the number of blocks to keep in cache so recently triggered appointments can be
            covered.

    Attributes:
        appointments (:obj:`dict`): a dictionary containing a summary of the appointments (:obj:`ExtendedAppointment
            <teos.extended_appointment.ExtendedAppointment>` instances) accepted by the tower (``locator`` and
            ``user_id``). It's populated trough ``add_appointment``.
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
        last_known_block (:obj:`str`): the last block known by the ``Watcher``.
        locator_cache (:obj:`LocatorCache`): a cache of locators for the last ``blocks_in_cache`` blocks.

    Raises:
        :obj:`InvalidKey <common.exceptions.InvalidKey>`: if teos sk cannot be loaded.

    """

    def __init__(self, db_manager, gatekeeper, block_processor, responder, sk_der, max_appointments, blocks_in_cache):
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
        self.locator_cache = LocatorCache(blocks_in_cache)

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
            so the appointment is rejected.
        """

        if len(self.appointments) >= self.max_appointments:
            message = "Maximum appointments reached, appointment rejected"
            logger.info(message, locator=appointment.locator)
            raise AppointmentLimitReached(message)

        user_id = self.gatekeeper.authenticate_user(appointment.serialize(), signature)
        # The user_id needs to be added to the ExtendedAppointment once the former has been authenticated
        appointment.user_id = user_id

        # The uuids are generated as the RIPEMD160(locator||user_pubkey).
        # If an appointment is requested by the user the uuid can be recomputed and queried straightaway (no maps).
        uuid = hash_160("{}{}".format(appointment.locator, user_id))

        # If this is a copy of an appointment we've already reacted to, the new appointment is rejected.
        if uuid in self.responder.trackers:
            message = "Appointment already in Responder"
            logger.info(message)
            raise AppointmentAlreadyTriggered(message)

        # Add the appointment to the Gatekeeper
        available_slots = self.gatekeeper.add_update_appointment(user_id, uuid, appointment)

        # Appointments that were triggered in blocks hold in the cache
        if appointment.locator in self.locator_cache.cache:
            try:
                dispute_txid = self.locator_cache.cache[appointment.locator]
                penalty_txid, penalty_rawtx = self.check_breach(uuid, appointment, dispute_txid)
                receipt = self.responder.handle_breach(
                    uuid, appointment.locator, dispute_txid, penalty_txid, penalty_rawtx, user_id, self.last_known_block
                )

                # At this point the appointment is accepted but data is only kept if it goes through the Responder.
                # Otherwise it is dropped.
                if receipt.delivered:
                    self.db_manager.store_watcher_appointment(uuid, appointment.to_dict())
                    self.db_manager.create_append_locator_map(appointment.locator, uuid)
                    self.db_manager.create_triggered_appointment_flag(uuid)

            except (EncryptionError, InvalidTransactionFormat):
                # If data inside the encrypted blob is invalid, the appointment is accepted but the data is dropped.
                # (same as with data that bounces in the Responder). This reduces the appointment slot count so it
                # could be used to discourage user misbehaviour.
                pass

        # Regular appointments that have not been triggered (or, at least, not recently)
        else:
            self.appointments[uuid] = appointment.get_summary()

            if appointment.locator in self.locator_uuid_map:
                # If the uuid is already in the map it means this is an update.
                if uuid not in self.locator_uuid_map[appointment.locator]:
                    self.locator_uuid_map[appointment.locator].append(uuid)
            else:
                # Otherwise two users have sent an appointment with the same locator, so we need to store both.
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
            "start_block": self.last_known_block,
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
            block = self.block_processor.get_block(block_hash)
            logger.info("New block received", block_hash=block_hash, prev_block_hash=block.get("previousblockhash"))

            # If a reorg is detected, the cache is fixed to cover the las `cache_size` blocks of the new chain
            if self.last_known_block != block.get("previousblockhash"):
                self.locator_cache.fix_cache(block_hash, self.block_processor)

            txids = block.get("tx")
            # Compute the locator for every transaction in the block and add them to the cache
            locator_txid_map = {compute_locator(txid): txid for txid in txids}
            self.locator_cache.cache.update(locator_txid_map)
            self.locator_cache.blocks[block_hash] = list(locator_txid_map.keys())
            logger.debug("Block added to cache", block_hash=block_hash)

            if len(self.appointments) > 0 and locator_txid_map:
                expired_appointments = self.gatekeeper.get_expired_appointments(block["height"])
                # Make sure we only try to delete what is on the Watcher (some appointments may have been triggered)
                expired_appointments = list(set(expired_appointments).intersection(self.appointments.keys()))

                # Keep track of the expired appointments before deleting them from memory
                appointments_to_delete_gatekeeper = {
                    uuid: self.appointments[uuid].get("user_id") for uuid in expired_appointments
                }

                Cleaner.delete_expired_appointments(
                    expired_appointments, self.appointments, self.locator_uuid_map, self.db_manager
                )

                valid_breaches, invalid_breaches = self.filter_breaches(self.get_breaches(locator_txid_map))

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

                # Update the dictionary with the completed appointments
                appointments_to_delete_gatekeeper.update(
                    {uuid: self.appointments[uuid].get("user_id") for uuid in appointments_to_delete}
                )

                Cleaner.delete_completed_appointments(
                    appointments_to_delete, self.appointments, self.locator_uuid_map, self.db_manager
                )

                # Remove expired and completed appointments from the Gatekeeper
                Cleaner.delete_gatekeeper_appointments(self.gatekeeper, appointments_to_delete_gatekeeper)

                if len(self.appointments) != 0:
                    logger.info("No more pending appointments")

            # Remove a block from the cache if the cache has reached its maximum size
            if self.locator_cache.is_full():
                self.locator_cache.remove_older_block()

            # Register the last processed block for the Watcher
            self.db_manager.store_last_block_hash_watcher(block_hash)
            self.last_known_block = block.get("hash")
            self.block_queue.task_done()

    def get_breaches(self, locator_txid_map):
        """
        Gets a dictionary of channel breaches given a map of locator:dispute_txid.

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
            logger.info("List of breaches", breaches=breaches)

        else:
            logger.info("No breaches found")

        return breaches

    def check_breach(self, uuid, appointment, dispute_txid):
        """
        Checks if a breach is valid. Valid breaches should decrypt to a valid transaction.

        Args:
            uuid (:obj:`str`): the uuid of the appointment that was triggered by the breach.
            appointment (:obj:`teos.extended_appointment.ExtendedAppointment`): the appointment data.
            dispute_txid (:obj:`str`): the id of the transaction that triggered the breach.

        Returns:
            :obj:`tuple`: A tuple containing the penalty txid and the raw penalty tx.

        Raises:
            :obj:`EncryptionError`: If the encrypted blob from the provided appointment cannot be decrypted with the
            key derived from the breach transaction id.
            :obj:`InvalidTransactionFormat`: If the decrypted data does not have a valid transaction format.
        """

        try:
            penalty_rawtx = Cryptographer.decrypt(appointment.encrypted_blob, dispute_txid)
            penalty_tx = self.block_processor.decode_raw_transaction(penalty_rawtx)

        except EncryptionError as e:
            logger.info("Transaction cannot be decrypted", uuid=uuid)
            raise e

        except InvalidTransactionFormat as e:
            logger.info("The breach contained an invalid transaction", uuid=uuid)
            raise e

        logger.info(
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
            :obj:`dict`: A dictionary containing all the breaches flagged either as valid or invalid.
            The structure is as follows:

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
