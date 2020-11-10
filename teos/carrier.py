from teos.logger import get_logger
from teos.tools import bitcoin_cli
import teos.utils.rpc_errors as rpc_errors
import bitcoin.rpc
from bitcoin.rpc import JSONRPCError, VerifyRejectedError, VerifyError, VerifyAlreadyInChainError
from bitcoin.core import x, lx, b2lx
from bitcoin.core.serialize import SerializationError, SerializationTruncationError
from common.errors import UNKNOWN_JSON_RPC_EXCEPTION, RPC_TX_REORGED_AFTER_BROADCAST

# FIXME: This class is not fully covered by unit tests


class Receipt:
    """
    The :class:`Receipt` class represent the interaction between the :obj:`Carrier` and ``bitcoind`` when broadcasting
    transactions. It is used to signal whether or not a transaction has been successfully broadcast and why.

    Args:
        delivered (:obj:`bool`): whether or not the transaction has been successfully broadcast.
        confirmations (:obj:`int`): the number of confirmations of the transaction to broadcast. In certain situations
            the :obj:`Carrier` may fail to broadcast a transaction because it was already in the blockchain.
            This attribute signals those situations.
        reason (:obj:`int`): an error code describing why the transaction broadcast failed.

    Returns:
         :obj:`Receipt`: A receipt describing whether or not the transaction was delivered. Notice that transactions
         that are already on chain are flagged as delivered with a ``confirmations > 0`` whereas new transactions are so
         with ``confirmations = 0``.
    """

    def __init__(self, delivered, confirmations=0, reason=None):
        self.delivered = delivered
        self.confirmations = confirmations
        self.reason = reason


class Carrier:
    """
    The :class:`Carrier` is in charge of interacting with ``bitcoind`` to send/get transactions. It uses :obj:`Receipt`
    objects to report about the sending outcome.

    Args:
        btc_connect_params (:obj:`dict`): a dictionary with the parameters to connect to bitcoind
            (``rpc user, rpc password, host and port``).

    Attributes:
        logger (:obj:`Logger <teos.logger.Logger>`): The logger for this component.
        issued_receipts (:obj:`dict`): A dictionary of issued receipts to prevent resending the same transaction over
            and over. It should periodically be reset to prevent it from growing unbounded.

    """

    def __init__(self, btc_connect_params):
        self.logger = get_logger(component=Carrier.__name__)
        self.btc_connect_params = btc_connect_params
        self.issued_receipts = {}

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

    # NOTCOVERED
    def send_transaction(self, rawtx, txid):
        """
        Tries to send a given raw transaction to the Bitcoin network using ``bitcoind``.

        Args:
            rawtx (:obj:`str`): a (potentially) signed raw transaction ready to be broadcast.
            txid  (:obj:`str`): the transaction id corresponding to ``rawtx``.

        Returns:
            :obj:`Receipt`: A receipt reporting whether the transaction was successfully delivered or not and why.
        """

        if txid in self.issued_receipts:
            self.logger.info("Transaction already sent", txid=txid)
            receipt = self.issued_receipts[txid]

            return receipt

        try:
            self.logger.info("Pushing transaction to the network", txid=txid, rawtx=rawtx)
            tx = bitcoin.core.CTransaction.deserialize(x(rawtx))
            self.proxy().sendrawtransaction(tx)

            receipt = Receipt(delivered=True)

        except (SerializationError, SerializationTruncationError) as e:
            receipt = Receipt(delivered=False, reason=rpc_errors.RPC_DESERIALIZATION_ERROR)
            self.logger.error("Transaction couldn't be broadcasted", error=e)

        # Since we're pushing a raw transaction to the network we can face several rejections
        except VerifyRejectedError as e:
            # DISCUSS: 37-transaction-rejection
            receipt = Receipt(delivered=False, reason=rpc_errors.RPC_VERIFY_REJECTED)
            self.logger.error("Transaction couldn't be broadcasted", error=e.error)

        except VerifyError as e:
            # DISCUSS: 37-transaction-rejection
            receipt = Receipt(delivered=False, reason=rpc_errors.RPC_VERIFY_ERROR)
            self.logger.error("Transaction couldn't be broadcasted", error=e.error)

        except VerifyAlreadyInChainError as e:
            self.logger.info("Transaction is already in the blockchain. Getting confirmation count", txid=txid)

            # If the transaction is already in the chain, we get the number of confirmations and watch the tracker
            # until the end of the appointment
            tx_info = self.get_transaction(txid)

            if tx_info is not None:
                confirmations = int(tx_info.get("confirmations"))
                receipt = Receipt(
                    delivered=True, confirmations=confirmations, reason=rpc_errors.RPC_VERIFY_ALREADY_IN_CHAIN
                )

            else:
                # There's a really unlikely edge case where a transaction can be reorged between receiving the
                # notification and querying the data. Notice that this implies the tx being also kicked off the
                # mempool, which again is really unlikely.
                receipt = Receipt(delivered=False, reason=RPC_TX_REORGED_AFTER_BROADCAST)

        except JSONRPCError as e:
            # Other errors that don't have a class in python-bitcoinlib

            errno = e.error.get("code")
            if errno == rpc_errors.RPC_DESERIALIZATION_ERROR:
                # Adding this here just for completeness. We should never end up here. The Carrier only sends txs
                # handed by the Responder, who receives them from the Watcher, who checks that the tx can be properly
                # deserialized
                self.logger.info("Transaction cannot be deserialized", txid=txid)
                receipt = Receipt(delivered=False, reason=rpc_errors.RPC_DESERIALIZATION_ERROR)

            else:
                # If something else happens (unlikely but possible) log it so we can treat it in future releases
                self.logger.error("JSONRPCError", method="Carrier.send_transaction", error=e.error)
                receipt = Receipt(delivered=False, reason=UNKNOWN_JSON_RPC_EXCEPTION)

        self.issued_receipts[txid] = receipt

        return receipt

    def get_transaction(self, txid):
        """
        Queries transaction data to ``bitcoind`` given a transaction id.

        Args:
            txid (:obj:`str`): a 32-byte hex-formatted string representing the transaction id.

        Returns:
            :obj:`dict` or :obj:`None`: A dictionary with the transaction data if the transaction can be found on the
            chain. :obj:`None` otherwise.
        """

        try:
            return self.proxy().getrawtransaction(lx(txid), verbose=True)

        except IndexError as e:
            # While it's quite unlikely, the transaction that was already in the blockchain could have been
            # reorged while we were querying bitcoind to get the confirmation count. In that case we just restart
            # the tracker

            self.logger.info("Transaction not found in mempool nor blockchain", txid=txid)
            return None

        except JSONRPCError as e:
            # If something else happens (unlikely but possible) log it so we can treat it in future releases
            self.logger.error("JSONRPCError", method="Carrier.get_transaction", error=e.error)

            return None
