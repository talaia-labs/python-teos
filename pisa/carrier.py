from pisa.rpc_errors import *
from pisa.logger import Logger
from pisa.tools import bitcoin_cli
from pisa.utils.auth_proxy import JSONRPCException
from pisa.errors import UNKNOWN_JSON_RPC_EXCEPTION, RPC_TX_REORGED_AFTER_BROADCAST

logger = Logger("Carrier")

# FIXME: This class is not fully covered by unit tests


class Receipt:
    """
    The ``Receipt`` class represent the interaction between the ``Carrier`` and ``bitcoind`` when broadcasting
    transactions. It is used to signal whether or not a transaction has been successfully broadcast and why.

    Args:
        delivered (bool): whether or not the transaction has been successfully broadcast.
        confirmations (int): the number of confirmations of the transaction to broadcast. In certain situations the
            ``Carrier`` may fail to broadcast a transaction because it was already in the blockchain. This attribute
            signals those situations.
        reason (int): an error code describing why the transaction broadcast failed.

    Returns:
         ``Receipt``: A receipt describing whether or not the transaction was delivered. Notice that transactions
         that are already on chain are flagged as delivered with a ``confirmations > 0`` whereas new transactions are so
         with ``confirmations = 0``.
    """

    def __init__(self, delivered, confirmations=0, reason=None):
        self.delivered = delivered
        self.confirmations = confirmations
        self.reason = reason


class Carrier:
    """
    The ``Carrier`` is the class in charge of interacting with ``bitcoind`` to send/get transactions. It uses
    ``Receipt`` objects to report about sending transactions.
    """

    # NOTCOVERED
    def send_transaction(self, rawtx, txid):
        """
        Tries to send a given raw transaction to the Bitcoin network using ``bitcoind``.

        Args:
            rawtx (str): a (potentially) signed raw transaction ready to be broadcast.
            txid  (str): the transaction id corresponding to ``rawtx``.

        Returns:
            ``Receipt``: A receipt reporting whether the transaction was successfully delivered or not and why.
        """

        try:
            logger.info("Pushing transaction to the network", txid=txid, rawtx=rawtx)
            bitcoin_cli().sendrawtransaction(rawtx)

            receipt = Receipt(delivered=True)

        except JSONRPCException as e:
            errno = e.error.get("code")
            # Since we're pushing a raw transaction to the network we can face several rejections
            if errno == RPC_VERIFY_REJECTED:
                # DISCUSS: 37-transaction-rejection
                # TODO: UNKNOWN_JSON_RPC_EXCEPTION is not the proper exception here. This is long due.
                receipt = Receipt(delivered=False, reason=UNKNOWN_JSON_RPC_EXCEPTION)

            elif errno == RPC_VERIFY_ERROR:
                # DISCUSS: 37-transaction-rejection
                receipt = Receipt(delivered=False, reason=RPC_VERIFY_ERROR)
                logger.error("Transaction couldn't be broadcast", error=e.error)

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
                    # notification and querying the data. Notice that this implies the tx being also kicked off the
                    # mempool, which again is really unlikely.
                    receipt = Receipt(delivered=False, reason=RPC_TX_REORGED_AFTER_BROADCAST)

            elif errno == RPC_DESERIALIZATION_ERROR:
                # Adding this here just for completeness. We should never end up here. The Carrier only sends txs
                # handed by the Responder, who receives them from the Watcher, who checks that the tx can be properly
                # deserialized
                logger.info("Transaction cannot be deserialized".format(txid))
                receipt = Receipt(delivered=False, reason=RPC_DESERIALIZATION_ERROR)

            else:
                # If something else happens (unlikely but possible) log it so we can treat it in future releases
                logger.error("JSONRPCException.", method="Carrier.send_transaction", error=e.error)
                receipt = Receipt(delivered=False, reason=UNKNOWN_JSON_RPC_EXCEPTION)

        return receipt

    @staticmethod
    def get_transaction(txid):
        """
        Queries transaction data to ``bitcoind`` given a transaction id.

        Args:
            txid (str): a 32-byte hex-formatted string representing the transaction id.

        Returns:
            ``dict`` or ``None``: A dictionary with the transaction data if the transaction can be found on the chain.
            Returns ``None`` otherwise.
        """

        try:
            tx_info = bitcoin_cli().getrawtransaction(txid, 1)

        except JSONRPCException as e:
            tx_info = None
            # While it's quite unlikely, the transaction that was already in the blockchain could have been
            # reorged while we were querying bitcoind to get the confirmation count. In such a case we just
            # restart the job
            if e.error.get("code") == RPC_INVALID_ADDRESS_OR_KEY:
                logger.info("Transaction not found in mempool nor blockchain", txid=txid)

            else:
                # If something else happens (unlikely but possible) log it so we can treat it in future releases
                logger.error("JSONRPCException.", method="Carrier.get_transaction", error=e.error)

        return tx_info
