from teos.logger import get_logger
import teos.utils.rpc_errors as rpc_errors
from common.exceptions import BasicException

import bitcoin.rpc
from bitcoin.rpc import JSONRPCError
from bitcoin.core import b2x, b2lx, lx


class InvalidTransactionFormat(BasicException):
    """Raised when a transaction is not properly formatted."""


class BlockProcessor:
    """
    The :class:`BlockProcessor` contains methods related to the blockchain. Most of its methods require communication
    with ``bitcoind``.

    Args:
        btc_connect_params (:obj:`dict`): a dictionary with the parameters to connect to bitcoind
            (``rpc user, rpc password, host and port``).

    Attributes:
        logger (:obj:`Logger <teos.logger.Logger>`): the logger for this component.
    """

    def __init__(self, btc_connect_params):
        self.logger = get_logger(component=BlockProcessor.__name__)
        self.btc_connect_params = btc_connect_params

    def proxy(self):
        """
        Returns a new ``http`` connection with ``bitcoind`` using the ``json-rpc`` interface, using
        ``btc_connect_params`` for the connectio parameters.

        Returns:
            :obj:`Proxy <bitcoin.rpc.Proxy>`: An authenticated service proxy to ``bitcoind``
            that can be used to send ``json-rpc`` commands.
        """

        service_url = "http://%s:%s@%s:%d" % (
            self.btc_connect_params.get("BTC_RPC_USER"),
            self.btc_connect_params.get("BTC_RPC_PASSWORD"),
            self.btc_connect_params.get("BTC_RPC_CONNECT"),
            self.btc_connect_params.get("BTC_RPC_PORT"),
        )
        return bitcoin.rpc.Proxy(service_url)

    def get_block(self, block_hash):
        """
        Gets a block given a block hash by querying ``bitcoind``.

        Args:
            block_hash (:obj:`str`): the block hash to be queried.

        Returns:
            :obj:`dict` or :obj:`None`: A dictionary containing the requested block data if the block is found.

            Returns :obj:`None` otherwise.
        """
        try:
            # by using "call" we obtain a dict, rather than a CBlock that we obtain calling .getblock().
            return self.proxy().call("getblock", block_hash)
        except JSONRPCError as e:
            self.logger.error("Couldn't get block from bitcoind", error=e.error)
            return None

    def get_best_block_hash(self):
        """
        Gets the hash of the current best chain tip.

        Returns:
            :obj:`str` or :obj:`None`: The hash of the block if it can be found.

            Returns :obj:`None` otherwise (not even sure this can actually happen).
        """
        try:
            return b2lx(self.proxy().getbestblockhash())
        except JSONRPCError as e:
            self.logger.error("Couldn't get block hash", error=e.error)
            return None

    def get_block_count(self):
        """
        Gets the block count of the best chain.

        Returns:
            :obj:`int` or :obj:`None`: The count of the best chain if it can be computed.

            Returns :obj:`None` otherwise (not even sure this can actually happen).
        """

        try:
            return self.proxy().getblockcount()
        except JSONRPCError as e:
            self.logger.error("Couldn't get block count", error=e.error)
            return None

    def decode_raw_transaction(self, raw_tx):
        """
        Deserializes a given raw transaction (hex encoded) and builds a dictionary representing it with all the
        associated metadata given by ``bitcoind`` (e.g. confirmation count).

        Args:
            raw_tx (:obj:`str`): the hex representation of the transaction.

        Returns:
            :obj:`dict`: The decoding of the given ``raw_tx`` if the transaction is well formatted.

        Raises:
            :obj:`InvalidTransactionFormat`: If the `provided ``raw_tx`` has invalid format.
            :obj:`JSONRPCError`: on any other error from the rpc call.
        """

        try:
            return self.proxy().call("decoderawtransaction", raw_tx)
        except JSONRPCError as e:
            errno = e.error.get("code")
            if errno == rpc_errors.RPC_DESERIALIZATION_ERROR:
                msg = "Cannot build transaction from decoded data"
                self.logger.error(msg, error=e.error)
                raise InvalidTransactionFormat(msg)
            else:
                self.logger.error(e.error.get("message"), error=e.error)
                raise e

    def get_distance_to_tip(self, target_block_hash):
        """
        Compute the distance between a given block hash and the best chain tip.

        Args:
            target_block_hash (:obj:`str`): the hash of the target block (the one to compute the distance form the tip).

        Returns:
            :obj:`int` or :obj:`None`: The distance between the target and the best chain tip is the target block can be
            found on the blockchain.

            Returns :obj:`None` otherwise.
        """

        distance = None

        chain_tip = self.get_best_block_hash()
        chain_tip_height = self.get_block(chain_tip).get("height")

        target_block = self.get_block(target_block_hash)

        if target_block is not None:
            target_block_height = target_block.get("height")

            distance = chain_tip_height - target_block_height

        return distance

    def get_missed_blocks(self, last_know_block_hash):
        """
        Gets the blocks between the current best chain tip and a given block hash (``last_know_block_hash``).

        This method is used to fetch all the missed information when recovering from a crash.

        Args:
            last_know_block_hash (:obj:`str`): the hash of the last known block.

        Returns:
            :obj:`list`: A list of blocks between the last given block and the current best chain tip, starting from the
            child of ``last_know_block_hash``.
        """

        current_block_hash = self.get_best_block_hash()
        missed_blocks = []

        while current_block_hash != last_know_block_hash and current_block_hash is not None:
            missed_blocks.append(current_block_hash)

            current_block = self.get_block(current_block_hash)
            current_block_hash = current_block.get("previousblockhash")

        return missed_blocks[::-1]

    def is_block_in_best_chain(self, block_hash):
        """
        Checks whether a given block is on the best chain or not. Blocks are identified by block_hash.

        A block that is not in the best chain will either not exists (block = None) or have a confirmation count of
        -1 (implying that the block was forked out or the chain never grew from that one).

        Args:
            block_hash(:obj:`str`): the hash of the block to be checked.

        Returns:
            :obj:`bool`: True if the block is on the best chain, False otherwise.

        Raises:
            KeyError: If the block cannot be found in the blockchain.
        """

        block = self.get_block(block_hash)

        if block is None:
            # This should never happen as long as we are using the same node, since bitcoind never drops orphan blocks
            # and we have received this block from our node at some point.
            raise KeyError("Block not found")

        if block.get("confirmations") != -1:
            return True
        else:
            return False

    def find_last_common_ancestor(self, last_known_block_hash):
        """
        Finds the last common ancestor between the current best chain tip and the last block known by us (older block).

        This is useful to recover from a chain fork happening while offline (crash/shutdown).

        Args:
            last_known_block_hash(:obj:`str`): the hash of the last know block.

        Returns:
            :obj:`tuple`: A tuple (:obj:`str`, :obj:`list`) where the first item contains the hash of the last common
            ancestor and the second item contains the list of transactions from ``last_known_block_hash`` to
            ``last_common_ancestor``.
        """

        target_block_hash = last_known_block_hash
        dropped_txs = []

        while not self.is_block_in_best_chain(target_block_hash):
            block = self.get_block(target_block_hash)
            dropped_txs.extend(block.get("tx"))
            target_block_hash = block.get("previousblockhash")

        return target_block_hash, dropped_txs
