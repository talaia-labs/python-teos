import pytest

from teos.carrier import Carrier
from bitcoind_mock.transaction import create_dummy_transaction
from test.teos.unit.conftest import generate_blocks, get_random_value_hex
from teos.rpc_errors import RPC_VERIFY_ALREADY_IN_CHAIN, RPC_DESERIALIZATION_ERROR


# FIXME: This test do not fully cover the carrier since the simulator does not support every single error bitcoind may
#        return for RPC_VERIFY_REJECTED and RPC_VERIFY_ERROR. Further development of the simulator / mocks or simulation
#        with bitcoind is required


sent_txs = []


@pytest.fixture(scope="module")
def carrier():
    return Carrier()


def test_send_transaction(run_bitcoind, carrier):
    tx = create_dummy_transaction()

    receipt = carrier.send_transaction(tx.hex(), tx.tx_id.hex())

    assert receipt.delivered is True


def test_send_double_spending_transaction(carrier):
    # We can test what happens if the same transaction is sent twice
    tx = create_dummy_transaction()
    txid = tx.tx_id.hex()

    receipt = carrier.send_transaction(tx.hex(), txid)
    sent_txs.append(txid)

    # Wait for a block to be mined. Issued receipts is reset from the Responder every block, so we should do it too.
    generate_blocks(2)
    carrier.issued_receipts = {}

    # Try to send it again
    receipt2 = carrier.send_transaction(tx.hex(), txid)

    # The carrier should report delivered True for both, but in the second case the transaction was already delivered
    # (either by himself or someone else)
    assert receipt.delivered is True
    assert receipt2.delivered is True and receipt2.confirmations >= 1 and receipt2.reason == RPC_VERIFY_ALREADY_IN_CHAIN


def test_send_transaction_invalid_format(carrier):
    # Test sending a transaction that does not fits the format
    txid = create_dummy_transaction().tx_id.hex()
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
