import pytest

from teos.tools import in_correct_network, get_default_rpc_port

from common.constants import MAINNET_RPC_PORT, TESTNET_RPC_PORT, REGTEST_RPC_PORT

from test.teos.unit.conftest import bitcoind_connect_params


def test_in_correct_network(run_bitcoind):
    # The simulator runs as if it was regtest, so every other network should fail
    assert in_correct_network(bitcoind_connect_params, "mainnet") is False
    assert in_correct_network(bitcoind_connect_params, "testnet") is False
    assert in_correct_network(bitcoind_connect_params, "regtest") is True


def test_get_default_rpc_port():
    # Not much to be tested here.
    assert get_default_rpc_port("mainnet") is MAINNET_RPC_PORT
    assert get_default_rpc_port("testnet") is TESTNET_RPC_PORT
    assert get_default_rpc_port("regtest") is REGTEST_RPC_PORT


def test_get_default_rpc_port_wrong():
    values = [0, "", 1.3, dict(), object(), None, "fakenet"]

    for v in values:
        with pytest.raises(ValueError):
            get_default_rpc_port(v)
