from teos.tools import can_connect_to_bitcoind, in_correct_network, bitcoin_cli
from test.teos.unit.conftest import bitcoind_connect_params


def test_in_correct_network(run_bitcoind):
    # The simulator runs as if it was regtest, so every other network should fail
    assert in_correct_network(bitcoind_connect_params, "mainnet") is False
    assert in_correct_network(bitcoind_connect_params, "testnet") is False
    assert in_correct_network(bitcoind_connect_params, "regtest") is True


def test_can_connect_to_bitcoind():
    assert can_connect_to_bitcoind(bitcoind_connect_params) is True


def test_bitcoin_cli(run_bitcoind):
    try:
        bitcoin_cli(bitcoind_connect_params).help()
        assert True

    except Exception:
        assert False
