import json
from time import sleep
from riemann.tx import Tx

from pisa import HOST, PORT
from apps.cli import pisa_cli
from pisa.utils.auth_proxy import JSONRPCException
from common.tools import compute_locator
from test.pisa.e2e.conftest import END_TIME_DELTA, build_appointment_data

# We'll use pisa_cli to add appointments. The expected input format is a list of arguments with a json-encoded
# appointment
pisa_cli.pisa_api_server = HOST
pisa_cli.pisa_api_port = PORT


def broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, addr):
    # Broadcast the commitment transaction and mine a block
    bitcoin_cli.sendrawtransaction(commitment_tx)
    bitcoin_cli.generatetoaddress(1, addr)


def get_appointment_info(locator):
    # Check that the justice has been triggered (the appointment has moved from Watcher to Responder)
    sleep(1)  # Let's add a bit of delay so the state can be updated
    return pisa_cli.get_appointment([locator])


def test_appointment_life_cycle(bitcoin_cli, create_txs):
    commitment_tx, penalty_tx = create_txs
    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx, penalty_tx)
    locator = compute_locator(appointment_data.get("tx_id"))

    assert pisa_cli.add_appointment([json.dumps(appointment_data)]) is True

    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    appointment_info = get_appointment_info(locator)

    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "dispute_responded"

    # It can be also checked by ensuring that the penalty transaction made it to the network
    penalty_tx_id = bitcoin_cli.decoderawtransaction(penalty_tx).get("txid")

    try:
        bitcoin_cli.getrawtransaction(penalty_tx_id)
        assert True

    except JSONRPCException:
        # If the transaction if not found.
        assert False

    # Now let's mine some blocks so the appointment reaches its end.
    # Since we are running all the nodes remotely data may take more time than normal, and some confirmations may be
    # missed, so we generate more than enough confirmations and add some delays.
    for _ in range(int(1.5 * END_TIME_DELTA)):
        sleep(1)
        bitcoin_cli.generatetoaddress(1, new_addr)

    appointment_info = get_appointment_info(locator)
    assert appointment_info[0].get("status") == "not_found"


def test_appointment_malformed_penalty(bitcoin_cli, create_txs):
    # Lets start by creating two valid transaction
    commitment_tx, penalty_tx = create_txs

    # Now we can modify the penalty so it is invalid when broadcast
    mod_penalty_tx = Tx.from_hex(penalty_tx)
    tx_in = mod_penalty_tx.tx_ins[0].copy(redeem_script=b"")
    mod_penalty_tx = mod_penalty_tx.copy(tx_ins=[tx_in])

    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx, mod_penalty_tx.hex())
    locator = compute_locator(appointment_data.get("tx_id"))

    assert pisa_cli.add_appointment([json.dumps(appointment_data)]) is True

    # Broadcast the commitment transaction and mine a block
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The appointment should have been removed since the penalty_tx was malformed.
    sleep(1)
    appointment_info = get_appointment_info(locator)

    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "not_found"
