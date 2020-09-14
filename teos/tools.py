from socket import timeout
from http.client import HTTPException

from teos.utils.auth_proxy import AuthServiceProxy, JSONRPCException

from common.constants import MAINNET_RPC_PORT, TESTNET_RPC_PORT, REGTEST_RPC_PORT

"""
Tools is a module with general methods that can used by different entities in the codebase.
"""


# NOTCOVERED
def bitcoin_cli(btc_connect_params):
    """
    An ``http`` connection with ``bitcoind`` using the ``json-rpc`` interface.

    Args:
        btc_connect_params (:obj:`dict`): a dictionary with the parameters to connect to bitcoind
            (``rpc user, rpc password, host and port``)

    Returns:
        :obj:`AuthServiceProxy <teos.utils.auth_proxy.AuthServiceProxy>`: An authenticated service proxy to ``bitcoind``
        that can be used to send ``json-rpc`` commands.
    """

    return AuthServiceProxy(
        "http://%s:%s@%s:%d"
        % (
            btc_connect_params.get("BTC_RPC_USER"),
            btc_connect_params.get("BTC_RPC_PASSWORD"),
            btc_connect_params.get("BTC_RPC_CONNECT"),
            btc_connect_params.get("BTC_RPC_PORT"),
        )
    )


# NOTCOVERED
def can_connect_to_bitcoind(btc_connect_params):
    """
    Checks if the tower has connection to ``bitcoind``.

    Args:
        btc_connect_params (:obj:`dict`): a dictionary with the parameters to connect to bitcoind
            (``rpc user, rpc password, host and port``).
    Returns:
        :obj:`bool`: True if the connection can be established. False otherwise.
    """

    can_connect = True

    try:
        bitcoin_cli(btc_connect_params).help()
    except (timeout, ConnectionRefusedError, JSONRPCException, HTTPException, OSError):
        can_connect = False

    return can_connect


def in_correct_network(btc_connect_params, network):
    """
    Checks if ``bitcoind`` and the tower are configured to run in the same network (``mainnet``, ``testnet`` or
    ``regtest``)

    Args:
        btc_connect_params (:obj:`dict`): a dictionary with the parameters to connect to bitcoind
            (rpc user, rpc password, host and port)
        network (:obj:`str`): the network the tower is connected to.

    Returns:
        :obj:`bool`: True if the network configuration matches. False otherwise.
    """

    mainnet_genesis_block_hash = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
    testnet3_genesis_block_hash = "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943"
    correct_network = False

    genesis_block_hash = bitcoin_cli(btc_connect_params).getblockhash(0)

    if network == "mainnet" and genesis_block_hash == mainnet_genesis_block_hash:
        correct_network = True
    elif network == "testnet" and genesis_block_hash == testnet3_genesis_block_hash:
        correct_network = True
    elif network == "regtest" and genesis_block_hash not in [mainnet_genesis_block_hash, testnet3_genesis_block_hash]:
        correct_network = True

    return correct_network


def get_default_rpc_port(network):
    """
    Returns the default RPC port given a network name.

    Args:
        network (:obj:`str`): the network name. Either ``mainnet``, ``testnet`` or ``regtest``.

    Returns:
        :obj:`int`: The default RPC port depending on the given network name.

    Raises:
        :obj:`ValueError`: If the network is not mainnet, testnet or regtest.
    """

    if network == "mainnet":
        return MAINNET_RPC_PORT
    elif network == "testnet":
        return TESTNET_RPC_PORT
    elif network == "regtest":
        return REGTEST_RPC_PORT
    else:
        raise ValueError("Wrong Bitcoin network. Expected: mainnet, testnet or regtest. Received: {}".format(network))


# Convenience method to ignore a signal
def ignore_signal(_, __):
    """Placeholder function to ignore signals sent to child processes so the main process can manage the teardown."""
    pass
