import pytest
from time import sleep
from riemann.tx import Tx
from binascii import hexlify
from coincurve import PrivateKey

from cli.exceptions import TowerResponseError
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

teos_base_endpoint = "http://{}:{}".format(cli_config.get("API_CONNECT"), cli_config.get("API_PORT"))
teos_add_appointment_endpoint = "{}/add_appointment".format(teos_base_endpoint)
teos_get_appointment_endpoint = "{}/get_appointment".format(teos_base_endpoint)

# Run teosd
teosd_process = run_teosd()

teos_pk, cli_sk, compressed_cli_pk = teos_cli.load_keys(
    cli_config.get("TEOS_PUBLIC_KEY"), cli_config.get("CLI_PRIVATE_KEY"), cli_config.get("CLI_PUBLIC_KEY")
)


def broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, addr):
    # Broadcast the commitment transaction and mine a block
    bitcoin_cli.sendrawtransaction(commitment_tx)
    bitcoin_cli.generatetoaddress(1, addr)


def get_appointment_info(locator, sk=cli_sk):
    sleep(1)  # Let's add a bit of delay so the state can be updated
    return teos_cli.get_appointment(locator, sk, teos_pk, teos_base_endpoint)


def add_appointment(appointment_data, sk=cli_sk):
    return teos_cli.add_appointment(appointment_data, sk, teos_pk, teos_base_endpoint)


def test_commands_non_registered(bitcoin_cli, create_txs):
    # All commands should fail if the user is not registered

    # Add appointment
    commitment_tx, penalty_tx = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)

    with pytest.raises(TowerResponseError):
        assert add_appointment(appointment_data)

    # Get appointment
    with pytest.raises(TowerResponseError):
        assert get_appointment_info(appointment_data.get("locator"))


def test_commands_registered(bitcoin_cli, create_txs):
    # Test registering and trying again
    teos_cli.register(compressed_cli_pk, teos_base_endpoint)

    # Add appointment
    commitment_tx, penalty_tx = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)

    appointment, available_slots = add_appointment(appointment_data)
    assert isinstance(appointment, Appointment) and isinstance(available_slots, str)

    # Get appointment
    r = get_appointment_info(appointment_data.get("locator"))
    assert r.get("locator") == appointment.locator
    assert r.get("appointment") == appointment.to_dict()


def test_appointment_life_cycle(bitcoin_cli, create_txs):
    # First of all we need to register
    teos_cli.register(compressed_cli_pk, teos_base_endpoint)

    # After that we can build an appointment and send it to the tower
    commitment_tx, penalty_tx = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)
    appointment, available_slots = add_appointment(appointment_data)

    # Get the information from the tower to check that it matches
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == "being_watched"
    assert appointment_info.get("locator") == locator
    assert appointment_info.get("appointment") == appointment.to_dict()

    # Trigger a breach and check again
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)
    appointment_info = get_appointment_info(locator)
    assert appointment_info is not None
    assert appointment_info.get("status") == "dispute_responded"
    assert appointment_info.get("locator") == locator

    # It can be also checked by ensuring that the penalty transaction made it to the network
    penalty_tx_id = bitcoin_cli.decoderawtransaction(penalty_tx).get("txid")

    try:
        bitcoin_cli.getrawtransaction(penalty_tx_id)
        assert True

    except JSONRPCException:
        # If the transaction is not found.
        assert False

    # Now let's mine some blocks so the appointment reaches its end.
    for _ in range(END_TIME_DELTA):
        bitcoin_cli.generatetoaddress(1, new_addr)

    # The appointment is no longer in the tower
    with pytest.raises(TowerResponseError):
        get_appointment_info(locator)


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

    appointment, _ = add_appointment(appointment_data)

    # Get the information from the tower to check that it matches
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == "being_watched"
    assert appointment_info.get("locator") == locator
    assert appointment_info.get("appointment") == appointment.to_dict()

    # Broadcast the commitment transaction and mine a block
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The appointment should have been removed since the penalty_tx was malformed.
    with pytest.raises(TowerResponseError):
        get_appointment_info(locator)


def test_appointment_wrong_decryption_key(bitcoin_cli, create_txs):
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

    signature = Cryptographer.sign(appointment.serialize(), cli_sk)
    data = {"appointment": appointment.to_dict(), "signature": signature}

    # Send appointment to the server.
    response = teos_cli.post_request(data, teos_add_appointment_endpoint)
    response_json = teos_cli.process_post_response(response)

    # Check that the server has accepted the appointment
    signature = response_json.get("signature")
    rpk = Cryptographer.recover_pk(appointment.serialize(), signature)
    assert Cryptographer.verify_rpk(teos_pk, rpk) is True
    assert response_json.get("locator") == appointment.locator

    # Trigger the appointment
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The appointment should have been removed since the decryption failed.
    with pytest.raises(TowerResponseError):
        get_appointment_info(appointment.locator)


def test_two_identical_appointments(bitcoin_cli, create_txs):
    # Tests sending two identical appointments to the tower.
    # This tests sending an appointment with two valid transaction with the same locator.
    # If they come from the same user, the last one will be kept.
    commitment_tx, penalty_tx = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")

    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    # Send the appointment twice
    add_appointment(appointment_data)
    add_appointment(appointment_data)

    # Broadcast the commitment transaction and mine a block
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The last appointment should have made it to the Responder
    appointment_info = get_appointment_info(locator)

    assert appointment_info.get("status") == "dispute_responded"
    assert appointment_info.get("appointment").get("penalty_rawtx") == penalty_tx


# FIXME: This test won't work since we're still passing appointment replicas to the Responder.
#        Uncomment when #88 is addressed
# def test_two_identical_appointments_different_users(bitcoin_cli, create_txs):
#     # Tests sending two identical appointments from different users to the tower.
#     # This tests sending an appointment with two valid transaction with the same locator.
#     # If they come from different users, both will be kept, but one will be dropped fro double-spending when passing to
#     # the responder
#     commitment_tx, penalty_tx = create_txs
#     commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
#
#     appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)
#     locator = compute_locator(commitment_tx_id)
#
#     # tmp keys from a different user
#     tmp_sk = PrivateKey()
#     tmp_compressed_pk = hexlify(tmp_sk.public_key.format(compressed=True)).decode("utf-8")
#     teos_cli.register(tmp_compressed_pk, teos_base_endpoint)
#
#     # Send the appointment twice
#     assert add_appointment(appointment_data) is True
#     assert add_appointment(appointment_data, sk=tmp_sk) is True
#
#     # Check that we can get it from both users
#     appointment_info = get_appointment_info(locator)
#     assert appointment_info.get("status") == "being_watched"
#     appointment_info = get_appointment_info(locator, sk=tmp_sk)
#     assert appointment_info.get("status") == "being_watched"
#
#     # Broadcast the commitment transaction and mine a block
#     new_addr = bitcoin_cli.getnewaddress()
#     broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)
#
#     # The last appointment should have made it to the Responder
#     sleep(1)
#     appointment_info = get_appointment_info(locator)
#     appointment_dup_info = get_appointment_info(locator, sk=tmp_sk)
#
#     # One of the two request must be None, while the other must be valid
#     assert (appointment_info is None and appointment_dup_info is not None) or (
#         appointment_dup_info is None and appointment_info is not None
#     )
#
#     appointment_info = appointment_info if appointment_info is None else appointment_dup_info
#
#     assert appointment_info.get("status") == "dispute_responded"
#     assert appointment_info.get("appointment").get("penalty_rawtx") == penalty_tx


def test_two_appointment_same_locator_different_penalty_different_users(bitcoin_cli, create_txs):
    # This tests sending an appointment with two valid transaction with the same locator fro different users
    commitment_tx, penalty_tx1 = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")

    # We need to create a second penalty spending from the same commitment
    decoded_commitment_tx = bitcoin_cli.decoderawtransaction(commitment_tx)
    new_addr = bitcoin_cli.getnewaddress()
    penalty_tx2 = create_penalty_tx(bitcoin_cli, decoded_commitment_tx, new_addr)

    appointment1_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx1)
    appointment2_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx2)
    locator = compute_locator(commitment_tx_id)

    # tmp keys for a different user
    tmp_sk = PrivateKey()
    tmp_compressed_pk = hexlify(tmp_sk.public_key.format(compressed=True)).decode("utf-8")
    teos_cli.register(tmp_compressed_pk, teos_base_endpoint)

    appointment, _ = add_appointment(appointment1_data)
    appointment_2, _ = add_appointment(appointment2_data, sk=tmp_sk)

    # Broadcast the commitment transaction and mine a block
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # One of the transactions must have made it to the Responder while the other must have been dropped for
    # double-spending. That means that one of the responses from the tower should fail
    appointment_info = None
    with pytest.raises(TowerResponseError):
        appointment_info = get_appointment_info(locator)
        appointment2_info = get_appointment_info(locator, sk=tmp_sk)

    if appointment_info is None:
        appointment_info = appointment2_info
        appointment1_data = appointment2_data

    assert appointment_info.get("status") == "dispute_responded"
    assert appointment_info.get("locator") == appointment1_data.get("locator")
    assert appointment_info.get("appointment").get("penalty_tx") == appointment1_data.get("penalty_tx")


def test_appointment_shutdown_teos_trigger_back_online(create_txs, bitcoin_cli):
    global teosd_process

    teos_pid = teosd_process.pid

    commitment_tx, penalty_tx = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    appointment, _ = add_appointment(appointment_data)

    # Restart teos
    teosd_process.terminate()
    teosd_process = run_teosd()

    assert teos_pid != teosd_process.pid

    # Check that the appointment is still in the Watcher
    appointment_info = get_appointment_info(locator)

    assert appointment_info.get("status") == "being_watched"
    assert appointment_info.get("appointment") == appointment.to_dict()

    # Trigger appointment after restart
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The appointment should have been moved to the Responder
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == "dispute_responded"


def test_appointment_shutdown_teos_trigger_while_offline(create_txs, bitcoin_cli):
    global teosd_process

    teos_pid = teosd_process.pid

    commitment_tx, penalty_tx = create_txs
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    appointment, _ = add_appointment(appointment_data)

    # Check that the appointment is still in the Watcher
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == "being_watched"
    assert appointment_info.get("appointment") == appointment.to_dict()

    # Shutdown and trigger
    teosd_process.terminate()
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # Restart
    teosd_process = run_teosd()
    assert teos_pid != teosd_process.pid

    # The appointment should have been moved to the Responder
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == "dispute_responded"

    teosd_process.terminate()
