import binascii
from hashlib import sha256

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

    # FIXME: The following two functions does not seem to belong here. They come from the Watcher, and need to be
    #        separated since they will be reused by the TimeTraveller.
    # DISCUSS: 36-who-should-check-appointment-trigger
    @staticmethod
    def get_potential_matches(txids, locator_uuid_map):
        potential_locators = {sha256(binascii.unhexlify(txid)).hexdigest(): txid for txid in txids}

        # Check is any of the tx_ids in the received block is an actual match
        intersection = set(locator_uuid_map.keys()).intersection(potential_locators.keys())
        potential_matches = {locator: potential_locators[locator] for locator in intersection}

        if len(potential_matches) > 0:
            logger.info("List of potential matches", potential_matches=potential_matches)

        else:
            logger.info("No potential matches found")

        return potential_matches

    @staticmethod
    # NOTCOVERED
    def get_matches(potential_matches, locator_uuid_map, appointments):
        matches = []

        for locator, dispute_txid in potential_matches.items():
            for uuid in locator_uuid_map[locator]:
                try:
                    # ToDo: #20-test-tx-decrypting-edge-cases
                    justice_rawtx = appointments[uuid].encrypted_blob.decrypt(dispute_txid)
                    justice_txid = bitcoin_cli().decoderawtransaction(justice_rawtx).get('txid')
                    logger.info("Match found for locator.", locator=locator, uuid=uuid, justice_txid=justice_txid)

                except JSONRPCException as e:
                    # Tx decode failed returns error code -22, maybe we should be more strict here. Leaving it simple
                    # for the POC
                    justice_txid = None
                    justice_rawtx = None
                    logger.error("Can't build transaction from decoded data.", error=e.error)

                matches.append((locator, uuid, dispute_txid, justice_txid, justice_rawtx))

        return matches

    # DISCUSS: This method comes from the Responder and seems like it could go back there.
    @staticmethod
    # NOTCOVERED
    def check_confirmations(txs, unconfirmed_txs, tx_job_map, missed_confirmations):

        for tx in txs:
            if tx in tx_job_map and tx in unconfirmed_txs:
                unconfirmed_txs.remove(tx)

                logger.info("Confirmation received for transaction", tx=tx)

            elif tx in unconfirmed_txs:
                if tx in missed_confirmations:
                    missed_confirmations[tx] += 1

                else:
                    missed_confirmations[tx] = 1

                logger.info("Transaction missed a confirmation", tx=tx, missed_confirmations=missed_confirmations[tx])

        return unconfirmed_txs, missed_confirmations
