from utils.authproxy import JSONRPCException
from pisa.rpc_errors import RPC_INVALID_ADDRESS_OR_KEY


def check_tx_in_chain(bitcoin_cli, tx_id, debug, logging, parent='', tx_label='transaction'):
    tx_in_chain = False
    confirmations = 0

    try:
        tx_info = bitcoin_cli.getrawtransaction(tx_id, 1)

        if tx_info.get("confirmations"):
            confirmations = int(tx_info.get("confirmations"))
            tx_in_chain = True
            if debug:
                logging.error("[{}] {} found in the blockchain (txid: {}) ".format(parent, tx_label, tx_id))
        elif debug:
            logging.error("[{}] {} found in mempool (txid: {}) ".format(parent, tx_label, tx_id))
    except JSONRPCException as e:
        if e.error.get('code') == RPC_INVALID_ADDRESS_OR_KEY:
            if debug:
                logging.error("[{}] {} not found in mempool nor blockchain (txid: {}) ".format(parent, tx_label, tx_id))
        elif debug:
            # ToDO: Unhandled errors, check this properly
            logging.error("[{}] JSONRPCException. Error code {}".format(parent, e))

    return tx_in_chain, confirmations
