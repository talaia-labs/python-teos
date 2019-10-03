import binascii
from hashlib import sha256

from pisa import logging, bitcoin_cli
from pisa.utils.auth_proxy import JSONRPCException


class BlockProcessor:
    @staticmethod
    def getblock(block_hash):
        block = None

        try:
            block = bitcoin_cli.getblock(block_hash)

        except JSONRPCException as e:
            logging.error("[BlockProcessor] couldn't get block from bitcoind. Error code {}".format(e))

        return block

    @staticmethod
    def get_potential_matches(txids, locator_uuid_map):
        potential_locators = {sha256(binascii.unhexlify(txid)).hexdigest(): txid for txid in txids}

        # Check is any of the tx_ids in the received block is an actual match
        intersection = set(locator_uuid_map.keys()).intersection(potential_locators.keys())
        potential_matches = {locator: potential_locators[locator] for locator in intersection}

        if len(potential_matches) > 0:
            logging.info("[BlockProcessor] list of potential matches: {}".format(potential_matches))

        else:
            logging.info("[BlockProcessor] no potential matches found")

    @staticmethod
    def get_matches(potential_matches, locator_uuid_map, appointments):
        matches = []

        for locator, dispute_txid in potential_matches.items():
            for uuid in locator_uuid_map[locator]:
                try:
                    # ToDo: #20-test-tx-decrypting-edge-cases
                    justice_rawtx = appointments[uuid].encrypted_blob.decrypt(binascii.unhexlify(dispute_txid))
                    justice_rawtx = binascii.hexlify(justice_rawtx).decode()
                    justice_txid = bitcoin_cli.decoderawtransaction(justice_rawtx).get('txid')
                    matches.append((locator, uuid, dispute_txid, justice_txid, justice_rawtx))

                    logging.info("[BlockProcessor] match found for locator {} (uuid: {}): {}".format(
                        locator, uuid, justice_txid))

                except JSONRPCException as e:
                    # Tx decode failed returns error code -22, maybe we should be more strict here. Leaving it simple
                    # for the POC
                    logging.error("[BlockProcessor] can't build transaction from decoded data. Error code {}".format(e))

        return matches

