import pytest

from pisa import c_logger
from pisa.carrier import Carrier
from test.simulator.utils import sha256d
from test.simulator.transaction import TX
from test.unit.conftest import generate_blocks, generate_block, get_random_value_hex
from pisa.rpc_errors import RPC_VERIFY_ALREADY_IN_CHAIN, RPC_DESERIALIZATION_ERROR

c_logger.disabled = True

# FIXME: This test do not fully cover the carrier since the simulator does not support every single error bitcoind may
#        return for RPC_VERIFY_REJECTED and RPC_VERIFY_ERROR. Further development of the simulator / mocks or simulation
#        with bitcoind is required


sent_txs = []


@pytest.fixture(scope="module")
def carrier():
    return Carrier()


def test_send_transaction(run_bitcoind, carrier):
    tx = TX.create_dummy_transaction()
    txid = sha256d(tx)

    receipt = carrier.send_transaction(tx, txid)

    assert receipt.delivered is True


def test_send_double_spending_transaction(carrier):
    # We can test what happens if the same transaction is sent twice
    tx = TX.create_dummy_transaction()
    txid = sha256d(tx)

    receipt = carrier.send_transaction(tx, txid)
    sent_txs.append(txid)

    # Wait for a block to be mined
    generate_blocks(2)

    # Try to send it again
    receipt2 = carrier.send_transaction(tx, txid)

    # The carrier should report delivered True for both, but in the second case the transaction was already delivered
    # (either by himself or someone else)
    assert receipt.delivered is True
    assert receipt2.delivered is True and receipt2.confirmations >= 1 and receipt2.reason == RPC_VERIFY_ALREADY_IN_CHAIN


def test_send_transaction_invalid_format(carrier):
    # Test sending a transaction that does not fits the format
    tx = TX.create_dummy_transaction()
    txid = sha256d(tx)
    receipt = carrier.send_transaction(txid, txid)

    assert receipt.delivered is False and receipt.reason == RPC_DESERIALIZATION_ERROR


def test_get_transaction():
    # We should be able to get back every transaction we've sent
    for tx in sent_txs:
        tx_info = Carrier.get_transaction(tx)

        assert tx_info is not None


def test_get_non_existing_transaction():
    tx_info = Carrier.get_transaction(get_random_value_hex(32))

    assert tx_info is None


def test_check_tx_in_chain(carrier):
    # Let's starts by looking for a random transaction
    random_tx = TX.create_dummy_transaction()
    random_txid = sha256d(random_tx)
    tx_in_chain, confirmations = carrier.check_tx_in_chain(random_txid)
    assert tx_in_chain is False and confirmations is None

    # We can now broadcast the transaction and check again
    carrier.send_transaction(random_tx, random_txid)
    tx_in_chain, confirmations = carrier.check_tx_in_chain(random_txid)

    # The tx should be on mempool now, so same
    assert tx_in_chain is False and confirmations is None

    # Finally we can mine a block and check again
    generate_block()
    tx_in_chain, confirmations = carrier.check_tx_in_chain(random_txid)

    assert tx_in_chain is True and confirmations == 1
