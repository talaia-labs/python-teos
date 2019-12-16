from common.logger import Logger
from pisa.tools import bitcoin_cli
from pisa.utils.auth_proxy import JSONRPCException

logger = Logger("BlockProcessor")


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
            logger.error("Couldn't get block from bitcoind.", error=e.error)

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
            logger.error("Couldn't get block hash.", error=e.error)

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
            logger.error("Can't build transaction from decoded data.", error=e.error)

        return tx

    def get_missed_blocks(self, last_know_block_hash):
        """
        Compute the blocks between the current best chain tip and a given block hash (``last_know_block_hash``).

        This method is used to fetch all the missed information when recovering from a crash. Note that if the two
        blocks are not part of the same chain, it would return all the blocks up to genesis.

        Args:
            last_know_block_hash (:obj:`str`): the hash of the last known block.

        Returns:
            :obj:`list`: A list of blocks between the last given block and the current best chain tip, starting from the
            child of ``last_know_block_hash``.
        """

        # FIXME: This needs to be integrated with the ChainMaester (soon TM) to allow dealing with forks.

        current_block_hash = self.get_best_block_hash()
        missed_blocks = []

        while current_block_hash != last_know_block_hash and current_block_hash is not None:
            missed_blocks.append(current_block_hash)

            current_block = self.get_block(current_block_hash)
            current_block_hash = current_block.get("previousblockhash")

        return missed_blocks[::-1]

    def get_distance_to_tip(self, target_block_hash):
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

        chain_tip = self.get_best_block_hash()
        chain_tip_height = self.get_block(chain_tip).get("height")

        target_block = self.get_block(target_block_hash)

        if target_block is not None:
            target_block_height = target_block.get("height")

            distance = chain_tip_height - target_block_height

        return distance
