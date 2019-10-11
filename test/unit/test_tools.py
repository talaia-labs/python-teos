import pytest
from time import sleep
from multiprocessing import Process


from pisa import logging
from pisa.tools import check_txid_format
from test.simulator.bitcoind_sim import run_simulator
from pisa.tools import can_connect_to_bitcoind, in_correct_network

logging.getLogger().disabled = True


@pytest.fixture(autouse=True, scope='session')
def run_bitcoind():
    bitcoind_process = Process(target=run_simulator)
    bitcoind_process.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)

    return bitcoind_process


def test_in_correct_network():
    # The simulator runs as if it was regtest, so every other network should fail
    assert in_correct_network('mainnet') is False
    assert in_correct_network('testnet') is False
    assert in_correct_network('regtest') is True


def test_can_connect_to_bitcoind():
    assert can_connect_to_bitcoind() is True


def test_can_connect_to_bitcoind_bitcoin_not_running(run_bitcoind):
    # Kill the simulator thread and test the check fails
    run_bitcoind.kill()
    assert can_connect_to_bitcoind() is False


def test_check_txid_format():
    assert(check_txid_format(None) is False)
    assert(check_txid_format("") is False)
    assert(check_txid_format(0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef) is False)  # wrong type
    assert(check_txid_format("abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd") is True)  # lowercase
    assert(check_txid_format("ABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCDEFABCD") is True)  # uppercase
    assert(check_txid_format("0123456789abcdef0123456789ABCDEF0123456789abcdef0123456789ABCDEF") is True)  # mixed case
    assert(check_txid_format("0123456789012345678901234567890123456789012345678901234567890123") is True)  # only nums
    assert(check_txid_format("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdf") is False)  # too short
    assert(check_txid_format("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0") is False)  # too long
    assert(check_txid_format("g123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef") is False)  # non-hex
