from queue import Queue
from threading import Thread

from teos.cleaner import Cleaner
from teos.chain_monitor import ChainMonitor
from teos.logger import get_logger
from common.constants import IRREVOCABLY_RESOLVED

CONFIRMATIONS_BEFORE_RETRY = 6
MIN_CONFIRMATIONS = 6


class TransactionTracker:
    """
    A :class:`TransactionTracker` is used to monitor a ``penalty_tx``. Once the dispute is seen by the
    :obj:`Watcher <teos.watcher.Watcher>` the penalty transaction is decrypted and the relevant appointment data is
    passed along to the :obj:`Responder`.

    Once the :obj:`Responder` has succeeded on broadcasting the penalty transaction it will create a
    :obj:`TransactionTracker` and monitor the blockchain until the end of the appointment.

    Args:
        locator (:obj:`str`): a 16-byte hex-encoded value used by the tower to detect channel breaches. It serves as a
            trigger for the tower to decrypt and broadcast the penalty transaction.
        dispute_txid (:obj:`str`): the id of the transaction that created the channel breach and triggered the penalty.
        penalty_txid (:obj:`str`): the id of the transaction that was encrypted under ``dispute_txid``.
        penalty_rawtx (:obj:`str`): the raw transaction that was broadcast as a consequence of the channel breach.
        user_id(:obj:`str`): the public key that identifies the user (33-bytes hex str).
    """

    def __init__(self, locator, dispute_txid, penalty_txid, penalty_rawtx, user_id):
        self.locator = locator
        self.dispute_txid = dispute_txid
        self.penalty_txid = penalty_txid
        self.penalty_rawtx = penalty_rawtx
        self.user_id = user_id

    @classmethod
    def from_dict(cls, tx_tracker_data):
        """
        Constructs a :obj:`TransactionTracker` instance from a dictionary. Requires that all the fields are populated
        (not :obj:`None`).

        Useful to load data from the database.

        Args:
            tx_tracker_data (:obj:`dict`): a dictionary with an entry per each field required to create the
                :obj:`TransactionTracker`.

        Returns:
            :obj:`TransactionTracker`: A transaction tracker instantiated with the provided data.

        Raises:
            :obj:`ValueError`: if any of the required fields is missing.
        """

        locator = tx_tracker_data.get("locator")
        dispute_txid = tx_tracker_data.get("dispute_txid")
        penalty_txid = tx_tracker_data.get("penalty_txid")
        penalty_rawtx = tx_tracker_data.get("penalty_rawtx")
        user_id = tx_tracker_data.get("user_id")

        if any(v is None for v in [locator, dispute_txid, penalty_txid, penalty_rawtx, user_id]):
            raise ValueError("Wrong transaction tracker data, some fields are missing")

        else:
            tx_tracker = cls(locator, dispute_txid, penalty_txid, penalty_rawtx, user_id)

        return tx_tracker

    def to_dict(self):
        """
        Encodes a :obj:`TransactionTracker` as a dictionary.

        Returns:
            :obj:`dict`: A dictionary containing the :obj:`TransactionTracker` data.
        """

        tx_tracker = {
            "locator": self.locator,
            "dispute_txid": self.dispute_txid,
            "penalty_txid": self.penalty_txid,
            "penalty_rawtx": self.penalty_rawtx,
            "user_id": self.user_id,
        }

        return tx_tracker

    def get_summary(self):
        """
        Returns the summary of a tracker, consisting on the locator, the user_id and the penalty_txid.

        Returns:
            :obj:`dict`: The appointment summary.
        """

        return {"locator": self.locator, "user_id": self.user_id, "penalty_txid": self.penalty_txid}


class Responder:
    """
    The :class:`Responder` is in charge of ensuring that channel breaches are dealt with. It does so handling
    the decrypted ``penalty_txs`` handed by the :obj:`Watcher <teos.watcher.Watcher>` and ensuring the they make it to
    the blockchain.

    Args:
        db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): an instance of the appointment
                database manager to interact with the database.
        carrier (:obj:`Carrier <teos.carrier.Carrier>`): a carrier instance to send transactions to bitcoind.
        block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): a block processor instance to
            get data from bitcoind.

    Attributes:
        logger (:obj:`Logger <teos.logger.Logger>`): The logger for this component.
        trackers (:obj:`dict`): A dictionary containing the minimum information about the :obj:`TransactionTracker`
            required by the :obj:`Responder` (``penalty_txid``, ``locator`` and ``user_id``). Each entry is identified
            by a ``uuid``.
        tx_tracker_map (:obj:`dict`): A ``penalty_txid:uuid`` map used to allow the :obj:`Responder` to deal with
            several trackers triggered by the same ``penalty_txid``.
        unconfirmed_txs (:obj:`list`): A list that keeps track of all unconfirmed ``penalty_txs``.
        missed_confirmations (:obj:`dict`): A dictionary that keeps count of how many confirmations each ``penalty_tx``
            has missed. Used to trigger rebroadcast if needed.
        block_queue (:obj:`Queue`): A queue used by the :obj:`Responder` to receive block hashes from ``bitcoind``. It
            is populated by the :obj:`ChainMonitor <teos.chain_monitor.ChainMonitor>`.
        db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): An instance of the appointment
                database manager to interact with the database.
        gatekeeper (:obj:`Gatekeeper <teos.gatekeeper.Gatekeeper>`): A `Gatekeeper` instance in charge to control the
            user access and subscription expiry.
        carrier (:obj:`Carrier <teos.carrier.Carrier>`): A carrier instance to send transactions to bitcoind.
        block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): A block processor instance to
            get data from bitcoind.
        last_known_block (:obj:`str`): The last block known by the :obj:`Responder`.
    """

    def __init__(self, db_manager, gatekeeper, carrier, block_processor):
        self.logger = get_logger(component=Responder.__name__)
        self.trackers = dict()
        self.tx_tracker_map = dict()
        self.unconfirmed_txs = []
        self.missed_confirmations = dict()
        self.block_queue = Queue()
        self.db_manager = db_manager
        self.gatekeeper = gatekeeper
        self.carrier = carrier
        self.block_processor = block_processor
        self.last_known_block = db_manager.load_last_block_hash_responder()

    def awake(self):
        """
            Starts a new thread to monitor the blockchain to make sure triggered appointments get enough depth.
            The thread will run until the :obj:`ChainMonitor` adds the ``ChainMonitor.END_MESSAGE`` to the queue.

            Returns:
                :obj:`Thread <multithreading.Thread>`: The thread object that was just created and is already running.
        """

        responder_thread = Thread(target=self.do_watch, daemon=True)
        responder_thread.start()
        return responder_thread

    def on_sync(self, block_hash):
        """
        Whether the :obj:`Responder` is on sync with ``bitcoind`` or not. Used when recovering from a crash.

        The Watchtower can be instantiated with fresh or with backed up data. In the later, some triggers may have been
        missed. In order to go back on sync both the :obj:`Watcher <teos.watcher.Watcher>` and the :obj:`Responder`
        need to perform the state transitions until they catch up.

        If a transaction is broadcast by the :obj:`Responder` and it is rejected (due to a double-spending for example)
        and the :obj:`Responder` is off-sync then the :obj:`TransactionTracker` is abandoned.

        This method helps making that decision.

        Args:
            block_hash (:obj:`str`): the block hash passed to the :obj:`Responder` in the ``handle_breach`` request.

        Returns:
            :obj:`bool`: Whether or not the :obj:`Responder` and ``bitcoind`` are on sync.
        """

        distance_from_tip = self.block_processor.get_distance_to_tip(block_hash)

        if distance_from_tip is not None and distance_from_tip > 1:
            synchronized = False

        else:
            synchronized = True

        return synchronized

    def handle_breach(self, uuid, locator, dispute_txid, penalty_txid, penalty_rawtx, user_id, block_hash):
        """
        Requests the :obj:`Responder` to handle a channel breach. This is the entry point of the :obj:`Responder`.

        Args:
            uuid (:obj:`str`): a unique identifier for the appointment.
            locator (:obj:`str`): the appointment locator provided by the user (16-byte hex-encoded).
            dispute_txid (:obj:`str`): the id of the transaction that created the channel breach.
            penalty_txid (:obj:`str`): the id of the decrypted transaction included in the appointment.
            penalty_rawtx (:obj:`str`): the raw transaction to be broadcast in response of the breach.
            user_id(:obj:`str`): the public key that identifies the user (33-bytes hex str).
            block_hash (:obj:`str`): the block hash at which the breach was seen (used to see if we are on sync).

        Returns:
            :obj:`Receipt <teos.carrier.Receipt>`: A receipt indicating whether or not the ``penalty_tx`` made it
            into the blockchain.
        """

        receipt = self.carrier.send_transaction(penalty_rawtx, penalty_txid)

        if receipt.delivered:
            self.add_tracker(uuid, locator, dispute_txid, penalty_txid, penalty_rawtx, user_id, receipt.confirmations)

        else:
            # TODO: Add the missing reasons (e.g. RPC_VERIFY_REJECTED)
            # TODO: Use self.on_sync(block_hash) to check whether or not we failed because we are out of sync
            self.logger.warning(
                "Tracker cannot be created", reason=receipt.reason, uuid=uuid, on_sync=self.on_sync(block_hash)
            )

        return receipt

    def add_tracker(self, uuid, locator, dispute_txid, penalty_txid, penalty_rawtx, user_id, confirmations=0):
        """
        Creates a :obj:`TransactionTracker` after successfully broadcasting a ``penalty_tx``.

        A summary of :obj:`TransactionTracker` is stored in ``trackers`` and ``tx_tracker_map`` and the ``penalty_txid``
        added to ``unconfirmed_txs`` if ``confirmations=0``. Finally, all the data is stored in the database.

        Args:
            uuid (:obj:`str`): a unique identifier for the appointment.
            locator (:obj:`str`): the appointment locator provided by the user (16-byte hex-encoded).
            dispute_txid (:obj:`str`): the id of the transaction that created the channel breach.
            penalty_txid (:obj:`str`): the id of the decrypted transaction included in the appointment.
            penalty_rawtx (:obj:`str`): the raw transaction to be broadcast.
            user_id(:obj:`str`): the public key that identifies the user (33-bytes hex str).
            confirmations (:obj:`int`): the confirmation count of the ``penalty_tx``. In normal conditions it will be
                zero, but if the transaction is already on the blockchain this won't be the case.
        """

        tracker = TransactionTracker(locator, dispute_txid, penalty_txid, penalty_rawtx, user_id)

        # We only store the penalty_txid, locator and user_id in memory. The rest is dumped into the db.
        self.trackers[uuid] = tracker.get_summary()

        if penalty_txid in self.tx_tracker_map:
            self.tx_tracker_map[penalty_txid].append(uuid)

        else:
            self.tx_tracker_map[penalty_txid] = [uuid]

        # In the case we receive two trackers with the same penalty txid we only add it to the unconfirmed txs list once
        if penalty_txid not in self.unconfirmed_txs and confirmations == 0:
            self.unconfirmed_txs.append(penalty_txid)

        self.db_manager.store_responder_tracker(uuid, tracker.to_dict())

        self.logger.info("New tracker added", dispute_txid=dispute_txid, penalty_txid=penalty_txid, user_id=user_id)

    def do_watch(self):
        """
        Monitors the blockchain for reorgs and appointment ends.

        This is the main method of the :obj:`Responder` and triggers tracker cleaning, rebroadcasting, reorg managing,
        etc.
        """

        # Distinguish fresh bootstraps from bootstraps from db
        if self.last_known_block is None:
            self.last_known_block = self.block_processor.get_best_block_hash()
            self.db_manager.store_last_block_hash_responder(self.last_known_block)

        while True:
            block_hash = self.block_queue.get()

            # When the ChainMonitor is stopped, a final ChainMonitor.END_MESSAGE is sent
            if block_hash == ChainMonitor.END_MESSAGE:
                break

            block = self.block_processor.get_block(block_hash)
            self.logger.info(
                "New block received", block_hash=block_hash, prev_block_hash=block.get("previousblockhash")
            )

            if len(self.trackers) > 0 and block is not None:
                txids = block.get("tx")

                if self.last_known_block == block.get("previousblockhash"):
                    completed_trackers = self.get_completed_trackers()
                    outdated_trackers = self.get_outdated_trackers(block.get("height"))
                    trackers_to_delete_gatekeeper = {
                        uuid: self.trackers[uuid].get("user_id") for uuid in completed_trackers
                    }

                    self.check_confirmations(txids)

                    Cleaner.delete_trackers(
                        completed_trackers, block.get("height"), self.trackers, self.tx_tracker_map, self.db_manager
                    )
                    Cleaner.delete_trackers(
                        outdated_trackers,
                        block.get("height"),
                        self.trackers,
                        self.tx_tracker_map,
                        self.db_manager,
                        outdated=True,
                    )
                    # Remove completed trackers from the gatekeeper.
                    with self.gatekeeper.lock:
                        Cleaner.delete_gatekeeper_appointments(
                            trackers_to_delete_gatekeeper, self.gatekeeper.registered_users, self.gatekeeper.user_db
                        )

                    self.rebroadcast(self.get_txs_to_rebroadcast())

                # NOTCOVERED
                else:
                    self.logger.warning(
                        "Reorg found",
                        local_prev_block_hash=self.last_known_block,
                        remote_prev_block_hash=block.get("previousblockhash"),
                    )

                    # ToDo: #24-properly-handle-reorgs
                    self.handle_reorgs(block_hash)

                # Clear the receipts issued in this block
                self.carrier.issued_receipts = {}

                if len(self.trackers) == 0:
                    self.logger.info("No more pending trackers")

            # Register the last processed block for the responder
            self.db_manager.store_last_block_hash_responder(block_hash)
            self.last_known_block = block.get("hash")
            self.block_queue.task_done()

    def check_confirmations(self, txs):
        """
        Checks if any of the monitored ``penalty_txs`` has received it's first confirmation or keeps missing them.

        This method manages ``unconfirmed_txs`` and ``missed_confirmations``.

        Args:
            txs (:obj:`list`): A list of confirmed tx ids (the list of transactions included in the last received
                block).
        """

        # If a new confirmed tx matches a tx we are watching, then we remove it from the unconfirmed txs map
        for tx in txs:
            if tx in self.tx_tracker_map and tx in self.unconfirmed_txs:
                self.unconfirmed_txs.remove(tx)

                self.logger.info("Confirmation received for transaction", tx=tx)

        # We also add a missing confirmation to all those txs waiting to be confirmed that have not been confirmed in
        # the current block
        for tx in self.unconfirmed_txs:
            if tx in self.missed_confirmations:
                self.missed_confirmations[tx] += 1
            else:
                self.missed_confirmations[tx] = 1

            self.logger.info(
                "Transaction missed a confirmation", tx=tx, missed_confirmations=self.missed_confirmations[tx]
            )

    def get_txs_to_rebroadcast(self):
        """
        Gets the transactions to be rebroadcast based on their ``missed_confirmation`` count.

        Returns:
            :obj:`list`: A list with all the ids of the transaction that have to be rebroadcast.
        """

        txs_to_rebroadcast = []

        for tx, missed_conf in self.missed_confirmations.items():
            if missed_conf >= CONFIRMATIONS_BEFORE_RETRY:
                # If a transactions has missed too many confirmations we add it to the rebroadcast list
                txs_to_rebroadcast.append(tx)

        return txs_to_rebroadcast

    def get_completed_trackers(self):
        """
        Gets the trackers that has already been fulfilled based on a given height (the justice transaction is
        irrevocably resolved).

        Returns:
            :obj:`list`: A list of completed trackers uuids.
        """

        completed_trackers = []
        # FIXME: This is here for duplicated penalties, we should be able to get rid of it once we prevent duplicates in
        #        the responder.
        checked_txs = {}

        # Avoiding dictionary changed size during iteration
        for uuid in list(self.trackers.keys()):
            penalty_txid = self.trackers[uuid].get("penalty_txid")
            if penalty_txid not in self.unconfirmed_txs:
                if penalty_txid not in checked_txs:
                    tx = self.carrier.get_transaction(penalty_txid)
                else:
                    tx = checked_txs.get(penalty_txid)

                if tx is not None:
                    confirmations = tx.get("confirmations")
                    checked_txs[penalty_txid] = tx

                    if confirmations is not None and confirmations >= IRREVOCABLY_RESOLVED:
                        completed_trackers.append(uuid)

        return completed_trackers

    def get_outdated_trackers(self, height):
        """
        Gets trackers than are outdated due to the user subscription being also outdated.

        Only gets those trackers which penalty transaction is not going trough (probably because of low fees), the rest
        will be eventually completed once they are irrevocably resolved.

        Args:
            height (:obj:`int`): the height of the last received block.

        Returns:
            :obj:`list`: A list of the outdated trackers uuids.
        """

        outdated_trackers = [
            uuid
            for uuid in self.gatekeeper.get_outdated_appointments(height)
            if self.trackers[uuid].get("penalty_txid") in self.unconfirmed_txs
        ]

        return outdated_trackers

    def rebroadcast(self, txs_to_rebroadcast):
        """
        Rebroadcasts a ``penalty_tx`` that has missed too many confirmations. In the current approach this will loop
        until the tracker expires if the penalty transactions keeps getting rejected due to fees.

        Potentially, the fees could be bumped here if the transaction has some tower dedicated outputs (or allows it
        trough ``ANYONECANPAY`` or something similar).

        Args:
            txs_to_rebroadcast (:obj:`list`): a list of transactions to be rebroadcast.

        Returns:
            :obj:`list`: A list of :obj:`Receipts <teos.carrier.Receipt>` with information about whether or not every
            transaction made it trough the network.
        """

        # DISCUSS: #22-discuss-confirmations-before-retry
        # ToDo: #23-define-behaviour-approaching-end

        receipts = []

        for txid in txs_to_rebroadcast:
            self.missed_confirmations[txid] = 0

            # FIXME: This would potentially grab multiple instances of the same transaction and try to send them.
            #   should we do it only once?
            for uuid in self.tx_tracker_map[txid]:
                tracker = TransactionTracker.from_dict(self.db_manager.load_responder_tracker(uuid))
                self.logger.warning(
                    "Transaction has missed many confirmations. Rebroadcasting", penalty_txid=tracker.penalty_txid
                )

                receipt = self.carrier.send_transaction(tracker.penalty_rawtx, tracker.penalty_txid)
                receipts.append((txid, receipt))

                if not receipt.delivered:
                    # FIXME: Can this actually happen?
                    self.logger.warning("Transaction failed", penalty_txid=tracker.penalty_txid)

        return receipts

    # NOTCOVERED
    def handle_reorgs(self, block_hash):
        """
        Basic reorg handle. It deals with situations where a reorg has been found but the ``dispute_tx`` is still
        on the chain. If the ``dispute_tx`` is reverted, it need to call the :obj:`ReorgManager` (Soon TM).

        Args:
            block_hash (:obj:`str`): the hash of the last block received (which triggered the reorg).

        """

        # Avoiding dictionary changed size during iteration
        for uuid in list(self.trackers.keys()):
            tracker = TransactionTracker.from_dict(self.db_manager.load_responder_tracker(uuid))

            # First we check if the dispute transaction is known (exists either in mempool or blockchain)
            dispute_tx = self.carrier.get_transaction(tracker.dispute_txid)

            if dispute_tx is not None:
                # If the dispute is there, we check the penalty
                penalty_tx = self.carrier.get_transaction(tracker.penalty_txid)

                if penalty_tx is not None:
                    # If the penalty exists we need to check is it's on the blockchain or not so we can update the
                    # unconfirmed transactions list accordingly.
                    if penalty_tx.get("confirmations") is None:
                        self.unconfirmed_txs.append(tracker.penalty_txid)

                        self.logger.info(
                            "Penalty transaction back in mempool. Updating unconfirmed transactions",
                            penalty_txid=tracker.penalty_txid,
                        )

                else:
                    # If the penalty transaction is missing, we need to reset the tracker.
                    self.handle_breach(
                        tracker.locator,
                        uuid,
                        tracker.dispute_txid,
                        tracker.penalty_txid,
                        tracker.penalty_rawtx,
                        tracker.user_id,
                        block_hash,
                    )

                    self.logger.warning(
                        "Penalty transaction banished. Resetting the tracker", penalty_tx=tracker.penalty_txid
                    )

            else:
                # ToDo: #24-properly-handle-reorgs
                # FIXME: if the dispute is not on chain (either in mempool or not there at all), we need to call the
                #        reorg manager
                self.logger.warning("Dispute and penalty transaction missing. Calling the reorg manager")
                self.logger.error("Reorg manager not yet implemented")
