import json
import binascii
from time import sleep
from riemann.tx import Tx

from teos import HOST, PORT

from cli import teos_cli, DATA_DIR, DEFAULT_CONF, CONF_FILE_NAME

import common.cryptographer
from common.blob import Blob
from common.logger import Logger
from common.tools import compute_locator
from common.appointment import Appointment
from common.cryptographer import Cryptographer
from teos.utils.auth_proxy import JSONRPCException
from test.teos.e2e.conftest import (
    END_TIME_DELTA,
    build_appointment_data,
    get_random_value_hex,
    create_penalty_tx,
    run_teosd,
    get_config,
)

cli_config = get_config(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF)
common.cryptographer.logger = Logger(actor="Cryptographer", log_name_prefix="")

# We'll use teos_cli to add appointments. The expected input format is a list of arguments with a json-encoded
# appointment
teos_cli.teos_api_server = "http://{}".format(HOST)
teos_cli.teos_api_port = PORT

# Run teosd
teosd_process = run_teosd()


def broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, addr):
    # Broadcast the commitment transaction and mine a block
    bitcoin_cli.sendrawtransaction(commitment_tx)
    bitcoin_cli.generatetoaddress(1, addr)


def get_appointment_info(locator):
    # Check that the justice has been triggered (the appointment has moved from Watcher to Responder)
    sleep(1)  # Let's add a bit of delay so the state can be updated
    return teos_cli.get_appointment(locator, cli_config)


def test_appointment_life_cycle(bitcoin_cli, create_txs):
    commitment_tx, penalty_tx = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    assert teos_cli.add_appointment([json.dumps(appointment_data)], cli_config) is True

    appointment_info = get_appointment_info(locator)
    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "being_watched"

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

    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, mod_penalty_tx.hex())
    locator = compute_locator(commitment_tx_id)

    assert teos_cli.add_appointment([json.dumps(appointment_data)], cli_config) is True

    # Broadcast the commitment transaction and mine a block
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The appointment should have been removed since the penalty_tx was malformed.
    sleep(1)
    appointment_info = get_appointment_info(locator)

    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "not_found"


def test_appointment_wrong_key(bitcoin_cli, create_txs):
    # This tests an appointment encrypted with a key that has not been derived from the same source as the locator.
    # Therefore the tower won't be able to decrypt the blob once the appointment is triggered.
    commitment_tx, penalty_tx = create_txs

    # The appointment data is built using a random 32-byte value.
    appointment_data = build_appointment_data(bitcoin_cli, get_random_value_hex(32), penalty_tx)

    # We can't use teos_cli.add_appointment here since it computes the locator internally, so let's do it manually.
    # We will encrypt the blob using the random value and derive the locator from the commitment tx.
    appointment_data["locator"] = compute_locator(bitcoin_cli.decoderawtransaction(commitment_tx).get("txid"))
    appointment_data["encrypted_blob"] = Cryptographer.encrypt(Blob(penalty_tx), get_random_value_hex(32))
    appointment = Appointment.from_dict(appointment_data)

    teos_pk, cli_sk, cli_pk_der = teos_cli.load_keys(
        cli_config.get("TEOS_PUBLIC_KEY"), cli_config.get("CLI_PRIVATE_KEY"), cli_config.get("CLI_PUBLIC_KEY")
    )
    hex_pk_der = binascii.hexlify(cli_pk_der)

    signature = Cryptographer.sign(appointment.serialize(), cli_sk)
    data = {"appointment": appointment.to_dict(), "signature": signature, "public_key": hex_pk_der.decode("utf-8")}

    # Send appointment to the server.
    response = teos_cli.post_appointment(data, cli_config)
    response_json = teos_cli.process_post_appointment_response(response)

    # Check that the server has accepted the appointment
    signature = response_json.get("signature")
    assert signature is not None
    rpk = Cryptographer.recover_pk(appointment.serialize(), signature)
    assert Cryptographer.verify_rpk(teos_pk, rpk) is True
    assert response_json.get("locator") == appointment.locator

    # Trigger the appointment
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The appointment should have been removed since the decryption failed.
    sleep(1)
    appointment_info = get_appointment_info(appointment.locator)

    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "not_found"


def test_two_identical_appointments(bitcoin_cli, create_txs):
    # Tests sending two identical appointments to the tower.
    # At the moment there are no checks for identical appointments, so both will be accepted, decrypted and kept until
    # the end.
    # TODO: 34-exact-duplicate-appointment
    # This tests sending an appointment with two valid transaction with the same locator.
    commitment_tx, penalty_tx = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")

    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    # Send the appointment twice
    assert teos_cli.add_appointment([json.dumps(appointment_data)], cli_config) is True
    assert teos_cli.add_appointment([json.dumps(appointment_data)], cli_config) is True

    # Broadcast the commitment transaction and mine a block
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The first appointment should have made it to the Responder, and the second one should have been dropped for
    # double-spending
    sleep(1)
    appointment_info = get_appointment_info(locator)

    assert appointment_info is not None
    assert len(appointment_info) == 2

    for info in appointment_info:
        assert info.get("status") == "dispute_responded"
        assert info.get("penalty_rawtx") == penalty_tx


def test_two_appointment_same_locator_different_penalty(bitcoin_cli, create_txs):
    # This tests sending an appointment with two valid transaction with the same locator.
    commitment_tx, penalty_tx1 = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")

    # We need to create a second penalty spending from the same commitment
    decoded_commitment_tx = bitcoin_cli.decoderawtransaction(commitment_tx)
    new_addr = bitcoin_cli.getnewaddress()
    penalty_tx2 = create_penalty_tx(bitcoin_cli, decoded_commitment_tx, new_addr)

    appointment1_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx1)
    appointment2_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx2)
    locator = compute_locator(commitment_tx_id)

    assert teos_cli.add_appointment([json.dumps(appointment1_data)], cli_config) is True
    assert teos_cli.add_appointment([json.dumps(appointment2_data)], cli_config) is True

    # Broadcast the commitment transaction and mine a block
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The first appointment should have made it to the Responder, and the second one should have been dropped for
    # double-spending
    sleep(1)
    appointment_info = get_appointment_info(locator)

    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "dispute_responded"
    assert appointment_info[0].get("penalty_rawtx") == penalty_tx1


def test_appointment_shutdown_teos_trigger_back_online(create_txs, bitcoin_cli):
    global teosd_process

    teos_pid = teosd_process.pid

    commitment_tx, penalty_tx = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    assert teos_cli.add_appointment([json.dumps(appointment_data)], cli_config) is True

    # Restart teos
    teosd_process.terminate()
    teosd_process = run_teosd()

    assert teos_pid != teosd_process.pid

    # Check that the appointment is still in the Watcher
    appointment_info = get_appointment_info(locator)

    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "being_watched"

    # Trigger appointment after restart
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The appointment should have been moved to the Responder
    sleep(1)
    appointment_info = get_appointment_info(locator)

    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "dispute_responded"


def test_appointment_shutdown_teos_trigger_while_offline(create_txs, bitcoin_cli):
    global teosd_process

    teos_pid = teosd_process.pid

    commitment_tx, penalty_tx = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    assert teos_cli.add_appointment([json.dumps(appointment_data)], cli_config) is True

    # Check that the appointment is still in the Watcher
    appointment_info = get_appointment_info(locator)
    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "being_watched"

    # Shutdown and trigger
    teosd_process.terminate()
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # Restart
    teosd_process = run_teosd()
    assert teos_pid != teosd_process.pid

    # The appointment should have been moved to the Responder
    sleep(1)
    appointment_info = get_appointment_info(locator)

    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "dispute_responded"

    teosd_process.terminate()
