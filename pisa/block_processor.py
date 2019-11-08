from pisa.logger import Logger
from pisa.tools import bitcoin_cli
from pisa.utils.auth_proxy import JSONRPCException

logger = Logger("BlockProcessor")


class BlockProcessor:
    @staticmethod
    def get_block(block_hash):

        try:
            block = bitcoin_cli().getblock(block_hash)

        except JSONRPCException as e:
            block = None
            logger.error("Couldn't get block from bitcoind.", error=e.error)

        return block

    @staticmethod
    def get_best_block_hash():

        try:
            block_hash = bitcoin_cli().getbestblockhash()

        except JSONRPCException as e:
            block_hash = None
            logger.error("Couldn't get block hash.", error=e.error)

        return block_hash

    @staticmethod
    def get_block_count():

        try:
            block_count = bitcoin_cli().getblockcount()

        except JSONRPCException as e:
            block_count = None
            logger.error("Couldn't get block count", error=e.error)

        return block_count

    @staticmethod
    def decode_raw_transaction(raw_tx):

        try:
            tx = bitcoin_cli().decoderawtransaction(raw_tx)

        except JSONRPCException as e:
            tx = None
            logger.error("Can't build transaction from decoded data.", error=e.error)

        return tx

    def get_missed_blocks(self, last_know_block_hash):
        current_block_hash = self.get_best_block_hash()
        missed_blocks = []

        while current_block_hash != last_know_block_hash and current_block_hash is not None:
            missed_blocks.append(current_block_hash)

            current_block = self.get_block(current_block_hash)
            current_block_hash = current_block.get("previousblockhash")

        return missed_blocks[::-1]

    def get_distance_to_tip(self, target_block_hash):
        distance = None

        chain_tip = self.get_best_block_hash()
        chain_tip_height = self.get_block(chain_tip).get("height")

        target_block = self.get_block(target_block_hash).get("height")

        if target_block is not None:
            target_block_height = target_block.get("height")

            distance = chain_tip_height - target_block_height

        return distance
