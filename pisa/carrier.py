from pisa.rpc_errors import *
from pisa import bitcoin_cli
from pisa.logger import Logger
from pisa.utils.auth_proxy import JSONRPCException
from pisa.errors import UNKNOWN_JSON_RPC_EXCEPTION

logger = Logger("Carrier")


class Receipt:
    def __init__(self, delivered, confirmations=0, reason=None):
        self.delivered = delivered
        self.confirmations = confirmations
        self.reason = reason


class Carrier:
    def send_transaction(self, rawtx, txid):
        try:
            logger.info("Pushing transaction to the network", txid=txid, rawtx=rawtx)
            bitcoin_cli.sendrawtransaction(rawtx)

            receipt = Receipt(delivered=True)

        except JSONRPCException as e:
            errno = e.error.get('code')
            # Since we're pushing a raw transaction to the network we can get two kind of rejections:
            # RPC_VERIFY_REJECTED and RPC_VERIFY_ALREADY_IN_CHAIN. The former implies that the transaction is rejected
            # due to network rules, whereas the later implies that the transaction is already in the blockchain.
            if errno == RPC_VERIFY_REJECTED:
                # DISCUSS: what to do in this case
                # DISCUSS: invalid transactions (properly formatted but invalid, like unsigned) fit here too.
                # DISCUSS: check errors -9 and -10
                # TODO: UNKNOWN_JSON_RPC_EXCEPTION is not the proper exception here. This is long due.
                receipt = Receipt(delivered=False, reason=UNKNOWN_JSON_RPC_EXCEPTION)

            elif errno == RPC_VERIFY_ERROR:
                # DISCUSS: The only reason for it seems to bea non-existing or spent input.
                #          https://github.com/bitcoin/bitcoin/blob/master/src/rpc/rawtransaction.cpp#L660
                #          However RPC_TRANSACTION_ERROR aliases RPC_VERIFY_ERROR and it's the default return for
                #          RPCErrorFromTransactionError
                #          https://github.com/bitcoin/bitcoin/blob/master/src/rpc/util.cpp#L276
                # TODO: UNKNOWN_JSON_RPC_EXCEPTION is not the proper exception here. This is long due.
                receipt = Receipt(delivered=False, reason=UNKNOWN_JSON_RPC_EXCEPTION)

            elif errno == RPC_VERIFY_ALREADY_IN_CHAIN:
                logger.info("Transaction is already in the blockchain. Getting confirmation count", txid=txid)

                # If the transaction is already in the chain, we get the number of confirmations and watch the job
                # until the end of the appointment
                tx_info = self.get_transaction(txid)

                if tx_info is not None:
                    confirmations = int(tx_info.get("confirmations"))
                    receipt = Receipt(delivered=True, confirmations=confirmations, reason=RPC_VERIFY_ALREADY_IN_CHAIN)

                else:
                    # There's a really unlikely edge case where a transaction can be reorged between receiving the
                    # notification and querying the data. In such a case we just resend
                    self.send_transaction(rawtx, txid)

            elif errno == RPC_DESERIALIZATION_ERROR:
                # Adding this here just for completeness. We should never end up here. The Carrier only sends txs
                # handed by the Responder, who receives them from the Watcher, who checks that the tx can be properly
                # deserialized
                logging.info("[Carrier] tx {} cannot be deserialized".format(txid))
                receipt = Receipt(delivered=False, reason=RPC_DESERIALIZATION_ERROR)

            else:
                # If something else happens (unlikely but possible) log it so we can treat it in future releases
                logger.error("JSONRPCException.", error_code=e)
                receipt = self.Receipt(delivered=False, reason=UNKNOWN_JSON_RPC_EXCEPTION)

        return receipt

    @staticmethod
    def get_transaction(txid):
        try:
            tx_info = bitcoin_cli.getrawtransaction(txid, 1)

        except JSONRPCException as e:
            tx_info = None
            # While it's quite unlikely, the transaction that was already in the blockchain could have been
            # reorged while we were querying bitcoind to get the confirmation count. In such a case we just
            # restart the job
            if e.error.get('code') == RPC_INVALID_ADDRESS_OR_KEY:
                logger.info("Transaction got reorged before obtaining information", txid=txid)

            # TODO: Check RPC methods to see possible returns and avoid general else
            # else:
            #     # If something else happens (unlikely but possible) log it so we can treat it in future releases
            #     logger.error("JSONRPCException.", error_code=e)

        return tx_info
