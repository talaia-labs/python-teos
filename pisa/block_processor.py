import binascii
from hashlib import sha256

from pisa import logging, bitcoin_cli, M
from pisa.utils.auth_proxy import JSONRPCException


class BlockProcessor:
    @staticmethod
    def get_block(block_hash):

        try:
            block = bitcoin_cli.getblock(block_hash)

        except JSONRPCException as e:
            block = None
            logging.error(M("[BlockProcessor] couldn't get block from bitcoind.", error_code=e))

        return block

    @staticmethod
    def get_best_block_hash():

        try:
            block_hash = bitcoin_cli.getbestblockhash()

        except JSONRPCException as e:
            block_hash = None
            logging.error(M("[BlockProcessor] couldn't get block hash.", error_code=e))

        return block_hash

    @staticmethod
    def get_block_count():

        try:
            block_count = bitcoin_cli.getblockcount()

        except JSONRPCException as e:
            block_count = None
            logging.error("[BlockProcessor] couldn't get block block count. Error code {}".format(e))

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
            logging.info(M("[BlockProcessor] list of potential matches", potential_matches=potential_matches))

        else:
            logging.info(M("[BlockProcessor] no potential matches found"))

        return potential_matches

        return potential_matches

    @staticmethod
    def get_matches(potential_matches, locator_uuid_map, appointments):
        matches = []

        for locator, dispute_txid in potential_matches.items():
            for uuid in locator_uuid_map[locator]:
                try:
                    # ToDo: #20-test-tx-decrypting-edge-cases
                    justice_rawtx = appointments[uuid].encrypted_blob.decrypt(dispute_txid)
                    justice_txid = bitcoin_cli.decoderawtransaction(justice_rawtx).get('txid')
                    matches.append((locator, uuid, dispute_txid, justice_txid, justice_rawtx))

                    logging.info(M("[BlockProcessor] match found for locator.", locator=locator, uuid=uuid, justice_txid=justice_txid))

                except JSONRPCException as e:
                    # Tx decode failed returns error code -22, maybe we should be more strict here. Leaving it simple
                    # for the POC
                    logging.error(M("[BlockProcessor] can't build transaction from decoded data.", error_code=e))

        return matches

    # DISCUSS: This method comes from the Responder and seems like it could go back there.
    @staticmethod
    def check_confirmations(txs, unconfirmed_txs, tx_job_map, missed_confirmations):

        for tx in txs:
            if tx in tx_job_map and tx in unconfirmed_txs:
                unconfirmed_txs.remove(tx)

                logging.info(M("[Responder] confirmation received for transaction", tx=tx))

            elif tx in unconfirmed_txs:
                if tx in missed_confirmations:
                    missed_confirmations[tx] += 1

                else:
                    missed_confirmations[tx] = 1

                logging.info(M("[Responder] transaction missed a confirmation", tx=tx, missed_confirmations=missed_confirmations[tx]))

        return unconfirmed_txs, missed_confirmations

