from teos.logger import get_logger
from common.exceptions import BasicException

from teos.tools import bitcoin_cli
from teos.utils.auth_proxy import JSONRPCException


class InvalidTransactionFormat(BasicException):
    """Raised when a transaction is not properly formatted."""


class BlockProcessor:
    """
    The :class:`BlockProcessor` contains methods related to the blockchain. Most of its methods require communication
    with ``bitcoind``.

    Args:
        btc_connect_params (:obj:`dict`): a dictionary with the parameters to connect to bitcoind
            (``rpc user, rpc password, host and port``).
        bitcoind_reachable (:obj:`threading.Event`): signals whether bitcoind is reachable or not.

    Attributes:
        logger (:obj:`Logger <teos.logger.Logger>`): the logger for this component.
    """

    def __init__(self, btc_connect_params, bitcoind_reachable):
        self.logger = get_logger(component=BlockProcessor.__name__)
        self.btc_connect_params = btc_connect_params
        self.bitcoind_reachable = bitcoind_reachable

    def _blocking_query(self, method):
        """
        Performs a query to bitcoind checking the ``bitcoin_reachable`` event. If the event is cleared, the query will
        block until it is set back. If bitcoind is unreachable but the event has still not been cleared, it will be
        cleared and the query will be performed again.

        This method is required since some methods of the ``BlockProcessor`` need to be called without a lock, while others
        do need it. For instance, request from the user (register, add_appointment, ...) need to be non-blocking, so the request
        fails if bitcoind is unreachable intead of being processed once it comes back online potentially once the request has timmed-out.
        On the other hand, request in the ``do_watch`` thread of the :obj:`teos.watcher.Watcher` and the :obj:`teos.responder.Responder`
        must have a response to proceed.

        Args:
            method (:obj:`function`): the BlockProcessor method to be called in a blocking way (usually a lambda).

        Returns:
            :obj:`Object`: The return of the called method.
        """

        self.bitcoind_reachable.wait()

        try:
            result = method()

        except ConnectionRefusedError:
            self.logger.error(f"Cannot connect to bitcoind. Waiting for it to come back online")
            self.bitcoind_reachable.clear()
            result = self._blocking_query(method)

        return result

    def get_block(self, block_hash, blocking=False):
        """
        Gets a block given a block hash by querying ``bitcoind``.

        Args:
            block_hash (:obj:`str`): the block hash to be queried.
            blocking (:obj:`bool`): whether the call should be blocking (wait for bitcoind to be available) or not.

        Returns:
            :obj:`dict` or :obj:`None`: A dictionary containing the requested block data if the block is found.

            Returns :obj:`None` otherwise.

        Raises:
            :obj:`ConnectionRefusedError`: if bitcoind cannot be reached.
        """

        if blocking:
            return self._blocking_query(lambda: self.get_block(block_hash))

        try:
            block = bitcoin_cli(self.btc_connect_params).getblock(block_hash)

        except JSONRPCException as e:
            block = None
            self.logger.error("Couldn't get block from bitcoind", error=e.error)

        return block

    def get_best_block_hash(self, blocking=False):
        """
        Gets the hash of the current best chain tip.

        Args:
            blocking (:obj:`bool`): whether the call should be blocking (wait for bitcoind to be available) or not.

        Returns:
            :obj:`str` or :obj:`None`: The hash of the block if it can be found.

            Returns :obj:`None` otherwise (not even sure this can actually happen).

        Raises:
            :obj:`ConnectionRefusedError`: if bitcoind cannot be reached.
        """

        if blocking:
            return self._blocking_query(lambda: self.get_best_block_hash())

        try:
            block_hash = bitcoin_cli(self.btc_connect_params).getbestblockhash()

        except JSONRPCException as e:
            block_hash = None
            self.logger.error("Couldn't get block hash", error=e.error)

        return block_hash

    def get_block_count(self, blocking=False):
        """
        Gets the block count of the best chain.

        Args:
            blocking (:obj:`bool`): whether the call should be blocking (wait for bitcoind to be available) or not.

        Returns:
            :obj:`int` or :obj:`None`: The count of the best chain if it can be computed.

            Returns :obj:`None` otherwise (not even sure this can actually happen).

        Raises:
            :obj:`ConnectionRefusedError`: if bitcoind cannot be reached.
        """

        if blocking:
            return self._blocking_query(lambda: self.get_block_count())

        try:
            block_count = bitcoin_cli(self.btc_connect_params).getblockcount()

        except JSONRPCException as e:
            block_count = None
            self.logger.error("Couldn't get block count", error=e.error)

        return block_count

    def decode_raw_transaction(self, raw_tx, blocking=False):
        """
        Deserializes a given raw transaction (hex encoded) and builds a dictionary representing it with all the
        associated metadata given by ``bitcoind`` (e.g. confirmation count).

        Args:
            raw_tx (:obj:`str`): the hex representation of the transaction.
            blocking (:obj:`bool`): whether the call should be blocking (wait for bitcoind to be available) or not.

        Returns:
            :obj:`dict`: The decoding of the given ``raw_tx`` if the transaction is well formatted.

        Raises:
            :obj:`InvalidTransactionFormat`: If the `provided ``raw_tx`` has invalid format.
            :obj:`ConnectionRefusedError`: if bitcoind cannot be reached.
        """

        if blocking:
            return self._blocking_query(lambda: self.decode_raw_transaction(raw_tx))

        try:
            tx = bitcoin_cli(self.btc_connect_params).decoderawtransaction(raw_tx)

        except JSONRPCException as e:
            msg = "Cannot build transaction from decoded data"
            self.logger.error(msg, error=e.error)
            raise InvalidTransactionFormat(msg)

        return tx

    def get_distance_to_tip(self, target_block_hash, blocking=False):
        """
        Compute the distance between a given block hash and the best chain tip.

        Args:
            target_block_hash (:obj:`str`): the hash of the target block (the one to compute the distance form the tip).
            blocking (:obj:`bool`): whether the call should be blocking (wait for bitcoind to be available) or not.

        Returns:
            :obj:`int` or :obj:`None`: The distance between the target and the best chain tip is the target block can be
            found on the blockchain.

            Returns :obj:`None` otherwise.

        Raises:
            :obj:`ConnectionRefusedError`: if bitcoind cannot be reached.
        """

        distance = None

        chain_tip = self.get_best_block_hash(blocking)
        chain_tip_height = self.get_block(chain_tip, blocking).get("height")

        target_block = self.get_block(target_block_hash, blocking)

        if target_block is not None:
            target_block_height = target_block.get("height")

            distance = chain_tip_height - target_block_height

        return distance

    def get_missed_blocks(self, last_know_block_hash, blocking=False):
        """
        Gets the blocks between the current best chain tip and a given block hash (``last_know_block_hash``).

        This method is used to fetch all the missed information when recovering from a crash.

        Args:
            last_know_block_hash (:obj:`str`): the hash of the last known block.
            blocking (:obj:`bool`): whether the call should be blocking (wait for bitcoind to be available) or not.

        Returns:
            :obj:`list`: A list of blocks between the last given block and the current best chain tip, starting from the
            child of ``last_know_block_hash``.

        Raises:
            :obj:`ConnectionRefusedError`: if bitcoind cannot be reached.
        """

        current_block_hash = self.get_best_block_hash(blocking)
        missed_blocks = []

        while current_block_hash != last_know_block_hash and current_block_hash is not None:
            missed_blocks.append(current_block_hash)

            current_block = self.get_block(current_block_hash, blocking)
            current_block_hash = current_block.get("previousblockhash")

        return missed_blocks[::-1]

    def is_block_in_best_chain(self, block_hash, blocking=False):
        """
        Checks whether a given block is on the best chain or not. Blocks are identified by block_hash.

        A block that is not in the best chain will either not exists (block = None) or have a confirmation count of
        -1 (implying that the block was forked out or the chain never grew from that one).

        Args:
            block_hash(:obj:`str`): the hash of the block to be checked.
            blocking (:obj:`bool`): whether the call should be blocking (wait for bitcoind to be available) or not.

        Returns:
            :obj:`bool`: True if the block is on the best chain, False otherwise.

        Raises:
            :obj:`KeyError`: if the block cannot be found in the blockchain.
            :obj:`ConnectionRefusedError`: if bitcoind cannot be reached.
        """

        block = self.get_block(block_hash, blocking)

        if block is None:
            # This should never happen as long as we are using the same node, since bitcoind never drops orphan blocks
            # and we have received this block from our node at some point.
            raise KeyError("Block not found")

        if block.get("confirmations") != -1:
            return True
        else:
            return False

    def find_last_common_ancestor(self, last_known_block_hash, blocking=False):
        """
        Finds the last common ancestor between the current best chain tip and the last block known by us (older block).

        This is useful to recover from a chain fork happening while offline (crash/shutdown).

        Args:
            last_known_block_hash(:obj:`str`): the hash of the last know block.
            blocking (:obj:`bool`): whether the call should be blocking (wait for bitcoind to be available) or not.

        Returns:
            :obj:`tuple`: A tuple (:obj:`str`, :obj:`list`) where the first item contains the hash of the last common
            ancestor and the second item contains the list of transactions from ``last_known_block_hash`` to
            ``last_common_ancestor``.

        Raises:
            :obj:`ConnectionRefusedError`: if bitcoind cannot be reached.
        """

        target_block_hash = last_known_block_hash
        dropped_txs = []

        while not self.is_block_in_best_chain(target_block_hash, blocking):
            block = self.get_block(target_block_hash, blocking)
            dropped_txs.extend(block.get("tx"))
            target_block_hash = block.get("previousblockhash")

        return target_block_hash, dropped_txs
