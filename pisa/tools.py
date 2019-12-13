from http.client import HTTPException

import pisa.conf as conf
from pisa.utils.auth_proxy import AuthServiceProxy, JSONRPCException

"""
Tools is a module with general methods that can used by different entities in the codebase.
"""


# NOTCOVERED
def bitcoin_cli():
    """
    An ``http`` connection with ``bitcoind`` using the ``json-rpc`` interface.

    Returns:
        :obj:`AuthServiceProxy <pisa.utils.auth_proxy.AuthServiceProxy>`: An authenticated service proxy to ``bitcoind``
        that can be used to send ``json-rpc`` commands.
    """

    return AuthServiceProxy(
        "http://%s:%s@%s:%d" % (conf.BTC_RPC_USER, conf.BTC_RPC_PASSWD, conf.BTC_RPC_HOST, conf.BTC_RPC_PORT)
    )


# NOTCOVERED
def can_connect_to_bitcoind():
    """
    Checks if the tower has connection to ``bitcoind``.

    Returns:
        :obj:`bool`: ``True`` if the connection can be established. ``False`` otherwise.
    """

    can_connect = True

    try:
        bitcoin_cli().help()
    except (ConnectionRefusedError, JSONRPCException, HTTPException):
        can_connect = False

    return can_connect


def in_correct_network(network):
    """
    Checks if ``bitcoind`` and the tower are configured to run in the same network (``mainnet``, ``testnet`` or
    ``regtest``)

    Returns:
        :obj:`bool`: ``True`` if the network configuration matches. ``False`` otherwise.
    """

    mainnet_genesis_block_hash = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
    testnet3_genesis_block_hash = "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943"
    correct_network = False

    genesis_block_hash = bitcoin_cli().getblockhash(0)

    if network == "mainnet" and genesis_block_hash == mainnet_genesis_block_hash:
        correct_network = True
    elif network == "testnet" and genesis_block_hash == testnet3_genesis_block_hash:
        correct_network = True
    elif network == "regtest" and genesis_block_hash not in [mainnet_genesis_block_hash, testnet3_genesis_block_hash]:
        correct_network = True

    return correct_network
