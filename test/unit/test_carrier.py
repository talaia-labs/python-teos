import pytest
from os import urandom
from time import sleep
from threading import Thread

from pisa.carrier import Carrier
from pisa.rpc_errors import RPC_VERIFY_ALREADY_IN_CHAIN, RPC_DESERIALIZATION_ERROR
from test.simulator.bitcoind_sim import run_simulator, TIME_BETWEEN_BLOCKS

# FIXME: This test do not fully cover the carrier since the simulator does not support every single error bitcoind may
#        return for RPC_VERIFY_REJECTED and RPC_VERIFY_ERROR. Further development of the simulator / mocks or simulation
#        with bitcoind is required


sent_txs = []


@pytest.fixture(autouse=True, scope='session')
def run_bitcoind():
    bitcoind_thread = Thread(target=run_simulator)
    bitcoind_thread.daemon = True
    bitcoind_thread.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)


@pytest.fixture(scope='session')
def carrier():
    return Carrier()


def test_send_transaction(carrier):
    # We are mocking bitcoind and in our simulator txid == tx
    tx = urandom(32).hex()
    receipt = carrier.send_transaction(tx, tx)

    assert(receipt.delivered is True)


def test_send_double_spending_transaction(carrier):
    # We can test what happens if the same transaction is sent twice
    tx = urandom(32).hex()
    receipt = carrier.send_transaction(tx, tx)
    sent_txs.append(tx)

    # Wait for a block to be mined
    sleep(TIME_BETWEEN_BLOCKS)

    # Try to send it again
    receipt2 = carrier.send_transaction(tx, tx)

    # The carrier should report delivered True for both, but in the second case the transaction was already delivered
    # (either by himself or someone else)
    assert(receipt.delivered is True)
    assert (receipt2.delivered is True and receipt2.confirmations == 1
            and receipt2.reason == RPC_VERIFY_ALREADY_IN_CHAIN)


def test_send_transaction_invalid_format(carrier):
    # Test sending a transaction that does not fits the format
    tx = urandom(31).hex()
    receipt = carrier.send_transaction(tx, tx)

    assert (receipt.delivered is False and receipt.reason == RPC_DESERIALIZATION_ERROR)


def test_get_transaction():
    # We should be able to get back every transaction we've sent
    for tx in sent_txs:
        tx_info = Carrier.get_transaction(tx)

        assert tx_info is not None


def test_get_non_existing_transaction():
    tx_info = Carrier.get_transaction(urandom(32).hex())

    assert tx_info is None


