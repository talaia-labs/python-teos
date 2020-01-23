from common.logger import Logger

from pisa import LOG_PREFIX
from pisa.tools import bitcoin_cli
from pisa.utils.auth_proxy import JSONRPCException

logger = Logger(actor="BlockProcessor", log_name_prefix=LOG_PREFIX)


class BlockProcessor:
    """
    The :class:`BlockProcessor` contains methods related to the blockchain. Most of its methods require communication
    with ``bitcoind``.
    """

    @staticmethod
    def get_block(block_hash):
        """
        Gives a block given a block hash by querying ``bitcoind``.

        Args:
            block_hash (:obj:`str`): The block hash to be queried.

        Returns:
            :obj:`dict` or :obj:`None`: A dictionary containing the requested block data if the block is found.

            Returns ``None`` otherwise.
        """

        try:
            block = bitcoin_cli().getblock(block_hash)

        except JSONRPCException as e:
            block = None
            logger.error("Couldn't get block from bitcoind", error=e.error)

        return block

    @staticmethod
    def get_best_block_hash():
        """
        Returns the hash of the current best chain tip.

        Returns:
            :obj:`str` or :obj:`None`: The hash of the block if it can be found.

            Returns ``None`` otherwise (not even sure this can actually happen).
        """

        try:
            block_hash = bitcoin_cli().getbestblockhash()

        except JSONRPCException as e:
            block_hash = None
            logger.error("Couldn't get block hash", error=e.error)

        return block_hash

    @staticmethod
    def get_block_count():
        """
        Returns the block height of the best chain.

        Returns:
            :obj:`int` or :obj:`None`: The block height if it can be computed.

            Returns ``None`` otherwise (not even sure this can actually happen).
        """

        try:
            block_count = bitcoin_cli().getblockcount()

        except JSONRPCException as e:
            block_count = None
            logger.error("Couldn't get block count", error=e.error)

        return block_count

    @staticmethod
    def decode_raw_transaction(raw_tx):
        """
        Deserializes a given raw transaction (hex encoded) and builds a dictionary representing it with all the
        associated metadata given by ``bitcoind`` (e.g. confirmation count).

        Args:
            raw_tx (:obj:`str`): The hex representation of the transaction.

        Returns:
            :obj:`dict` or :obj:`None`: The decoding of the given ``raw_tx`` if the transaction is well formatted.

            Returns ``None`` otherwise.
        """

        try:
            tx = bitcoin_cli().decoderawtransaction(raw_tx)

        except JSONRPCException as e:
            tx = None
            logger.error("Can't build transaction from decoded data", error=e.error)

        return tx

    @staticmethod
    def get_distance_to_tip(target_block_hash):
        """
        Compute the distance between a given block hash and the best chain tip.

        Args:
            target_block_hash (:obj:`str`): the hash of the target block (the one to compute the distance form the tip).

        Returns:
            :obj:`int` or :obj:`None`: The distance between the target and the best chain tip is the target block can be
            found on the blockchain.

            Returns ``None`` otherwise.
        """

        distance = None

        chain_tip = BlockProcessor.get_best_block_hash()
        chain_tip_height = BlockProcessor.get_block(chain_tip).get("height")

        target_block = BlockProcessor.get_block(target_block_hash)

        if target_block is not None:
            target_block_height = target_block.get("height")

            distance = chain_tip_height - target_block_height

        return distance

    @staticmethod
    def get_missed_blocks(last_know_block_hash):
        """
        Compute the blocks between the current best chain tip and a given block hash (``last_know_block_hash``).

        This method is used to fetch all the missed information when recovering from a crash.

        Args:
            last_know_block_hash (:obj:`str`): the hash of the last known block.

        Returns:
            :obj:`list`: A list of blocks between the last given block and the current best chain tip, starting from the
            child of ``last_know_block_hash``.
        """

        current_block_hash = BlockProcessor.get_best_block_hash()
        missed_blocks = []

        while current_block_hash != last_know_block_hash and current_block_hash is not None:
            missed_blocks.append(current_block_hash)

            current_block = BlockProcessor.get_block(current_block_hash)
            current_block_hash = current_block.get("previousblockhash")

        return missed_blocks[::-1]

    @staticmethod
    def is_block_in_best_chain(block_hash):
        """
        Checks whether or not a given block is on the best chain. Blocks are identified by block_hash.

        A block that is not in the best chain will either not exists (block = None) or have a confirmation count of
        -1 (implying that the block was forked out or the chain never grew from that one).

        Args:
            block_hash(:obj:`str`): the hash of the block to be checked.

        Returns:
            :obj:`bool`: ``True`` if the block is on the best chain, ``False`` otherwise.

        Raises:
            KeyError: If the block cannot be found in the blockchain.
        """

        block = BlockProcessor.get_block(block_hash)

        if block is None:
            # This should never happen as long as we are using the same node, since bitcoind never drops orphan blocks
            # and we have received this block from our node at some point.
            raise KeyError("Block not found")

        if block.get("confirmations") != -1:
            return True
        else:
            return False

    @staticmethod
    def find_last_common_ancestor(last_known_block_hash):
        """
        Finds the last common ancestor between the current best chain tip and the last block known by us (older block).

        This is useful to recover from a chain fork happening while offline (crash/shutdown).

        Args:
            last_known_block_hash(:obj:`str`): the hash of the last know block.

        Returns:
            :obj:`tuple`: A tuple (:obj:`str`:, :obj:`list`:) where the first item contains the hash of the last common
                ancestor and the second item contains the list of transactions from ``last_known_block_hash`` to
                ``last_common_ancestor``.
        """

        target_block_hash = last_known_block_hash
        dropped_txs = []

        while not BlockProcessor.is_block_in_best_chain(target_block_hash):
            block = BlockProcessor.get_block(target_block_hash)
            dropped_txs.extend(block.get("tx"))
            target_block_hash = block.get("previousblockhash")

        return target_block_hash, dropped_txs
