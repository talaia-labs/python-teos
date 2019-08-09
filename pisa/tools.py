from pisa.utils.authproxy import JSONRPCException
from pisa.rpc_errors import RPC_INVALID_ADDRESS_OR_KEY
from http.client import HTTPException


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


def can_connect_to_bitcoind(bitcoin_cli):
    can_connect = True

    try:
        bitcoin_cli.help()
    except (ConnectionRefusedError, JSONRPCException, HTTPException):
        can_connect = False

    return can_connect


def in_correct_network(bitcoin_cli, network):
    mainnet_genesis_block_hash = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
    testnet3_genesis_block_hash = "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943"
    correct_network = False

    genesis_block_hash = bitcoin_cli.getblockhash(0)

    if network == 'mainnet' and genesis_block_hash == mainnet_genesis_block_hash:
        correct_network = True
    elif network == 'testnet' and genesis_block_hash == testnet3_genesis_block_hash:
        correct_network = True
    elif network == 'regtest' and genesis_block_hash not in [mainnet_genesis_block_hash, testnet3_genesis_block_hash]:
        correct_network = True

    return correct_network

