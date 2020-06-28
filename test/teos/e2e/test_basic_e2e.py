import json
import pytest
from time import sleep
from riemann.tx import Tx
from binascii import hexlify
from coincurve import PrivateKey

from cli.exceptions import TowerResponseError
from cli import teos_cli, DATA_DIR, DEFAULT_CONF, CONF_FILE_NAME

from common.tools import compute_locator
from common.appointment import Appointment
from common.cryptographer import Cryptographer

from teos import DEFAULT_CONF as TEOS_CONF
from teos import DATA_DIR as TEOS_DATA_DIR
from teos import CONF_FILE_NAME as TEOS_CONF_FILE_NAME
from teos.utils.auth_proxy import JSONRPCException

from test.teos.e2e.conftest import (
    build_appointment_data,
    get_random_value_hex,
    create_penalty_tx,
    run_teosd,
    get_config,
    create_txs,
)

cli_config = get_config(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF)
teos_config = get_config(TEOS_DATA_DIR, TEOS_CONF_FILE_NAME, TEOS_CONF)


teos_base_endpoint = "http://{}:{}".format(cli_config.get("API_CONNECT"), cli_config.get("API_PORT"))
teos_add_appointment_endpoint = "{}/add_appointment".format(teos_base_endpoint)
teos_get_appointment_endpoint = "{}/get_appointment".format(teos_base_endpoint)
teos_get_all_appointments_endpoint = "{}/get_all_appointments".format(teos_base_endpoint)

# Run teosd
teosd_process = run_teosd()

teos_id, user_sk, user_id = teos_cli.load_keys(cli_config.get("TEOS_PUBLIC_KEY"), cli_config.get("CLI_PRIVATE_KEY"))

appointments_in_watcher = 0
appointments_in_responder = 0


def broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, addr):
    # Broadcast the commitment transaction and mine a block
    bitcoin_cli.sendrawtransaction(commitment_tx)
    bitcoin_cli.generatetoaddress(1, addr)


def get_appointment_info(locator, sk=user_sk):
    sleep(1)  # Let's add a bit of delay so the state can be updated
    return teos_cli.get_appointment(locator, sk, teos_id, teos_base_endpoint)


def add_appointment(appointment_data, sk=user_sk):
    return teos_cli.add_appointment(appointment_data, sk, teos_id, teos_base_endpoint)


def get_all_appointments():
    r = teos_cli.get_all_appointments(teos_base_endpoint)
    return json.loads(r)


def test_commands_non_registered(bitcoin_cli):
    # All commands should fail if the user is not registered

    # Add appointment
    commitment_tx, penalty_tx = create_txs(bitcoin_cli)
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(commitment_tx_id, penalty_tx)

    with pytest.raises(TowerResponseError):
        appointment = teos_cli.create_appointment(appointment_data)
        add_appointment(appointment)

    # Get appointment
    with pytest.raises(TowerResponseError):
        assert get_appointment_info(appointment_data.get("locator"))


def test_commands_registered(bitcoin_cli):
    global appointments_in_watcher

    # Test registering and trying again
    teos_cli.register(user_id, teos_base_endpoint)

    # Add appointment
    commitment_tx, penalty_tx = create_txs(bitcoin_cli)
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(commitment_tx_id, penalty_tx)

    appointment = teos_cli.create_appointment(appointment_data)
    add_appointment(appointment)

    # Get appointment
    r = get_appointment_info(appointment_data.get("locator"))
    assert r.get("locator") == appointment.locator
    assert r.get("appointment") == appointment.to_dict()
    appointments_in_watcher += 1


def test_appointment_life_cycle(bitcoin_cli):
    global appointments_in_watcher, appointments_in_responder

    # First of all we need to register
    response = teos_cli.register(user_id, teos_base_endpoint)
    available_slots = response.get("available_slots")

    # After that we can build an appointment and send it to the tower
    commitment_tx, penalty_tx = create_txs(bitcoin_cli)
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)
    appointment = teos_cli.create_appointment(appointment_data)
    add_appointment(appointment)
    appointments_in_watcher += 1

    # Get the information from the tower to check that it matches
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == "being_watched"
    assert appointment_info.get("locator") == locator
    assert appointment_info.get("appointment") == appointment.to_dict()

    # Check also the get_all_appointment endpoint
    all_appointments = get_all_appointments()
    watching = all_appointments.get("watcher_appointments")
    responding = all_appointments.get("responder_trackers")
    assert len(watching) == appointments_in_watcher and len(responding) == 0

    # Trigger a breach and check again
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == "dispute_responded"
    assert appointment_info.get("locator") == locator
    appointments_in_watcher -= 1
    appointments_in_responder += 1

    all_appointments = get_all_appointments()
    watching = all_appointments.get("watcher_appointments")
    responding = all_appointments.get("responder_trackers")
    assert len(watching) == appointments_in_watcher and len(responding) == appointments_in_responder

    # It can be also checked by ensuring that the penalty transaction made it to the network
    penalty_tx_id = bitcoin_cli.decoderawtransaction(penalty_tx).get("txid")

    try:
        bitcoin_cli.getrawtransaction(penalty_tx_id)
        assert True

    except JSONRPCException:
        # If the transaction is not found.
        assert False

    # Now let's mine some blocks so the appointment reaches its end. We need 100 + EXPIRY_DELTA -1
    bitcoin_cli.generatetoaddress(100 + teos_config.get("EXPIRY_DELTA") - 1, new_addr)
    appointments_in_responder -= 1

    # The appointment is no longer in the tower
    with pytest.raises(TowerResponseError):
        get_appointment_info(locator)

    # Check that the appointment is not in the Gatekeeper by checking the available slots (should have increase by 1)
    # We can do so by topping up the subscription (FIXME: find a better way to check this).
    response = teos_cli.register(user_id, teos_base_endpoint)
    assert (
        response.get("available_slots")
        == available_slots
        + teos_config.get("SUBSCRIPTION_SLOTS")
        + 1
        - appointments_in_watcher
        - appointments_in_responder
    )


def test_multiple_appointments_life_cycle(bitcoin_cli):
    global appointments_in_watcher, appointments_in_responder
    # Tests that get_all_appointments returns all the appointments the tower is storing at various stages in the
    # appointment lifecycle.
    appointments = []

    commitment_txs, penalty_txs = create_txs(bitcoin_cli, n=5)

    # Create five appointments.
    for commitment_tx, penalty_tx in zip(commitment_txs, penalty_txs):
        commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
        appointment_data = build_appointment_data(commitment_tx_id, penalty_tx)

        locator = compute_locator(commitment_tx_id)
        appointment = {
            "locator": locator,
            "commitment_tx": commitment_tx,
            "penalty_tx": penalty_tx,
            "appointment_data": appointment_data,
        }

        appointments.append(appointment)

    # Send all of them to watchtower.
    for appt in appointments:
        appointment = teos_cli.create_appointment(appt.get("appointment_data"))
        add_appointment(appointment)
        appointments_in_watcher += 1

    # Two of these appointments are breached, and the watchtower responds to them.
    breached_appointments = []
    for i in range(2):
        new_addr = bitcoin_cli.getnewaddress()
        broadcast_transaction_and_mine_block(bitcoin_cli, appointments[i]["commitment_tx"], new_addr)
        bitcoin_cli.generatetoaddress(1, new_addr)
        breached_appointments.append(appointments[i]["locator"])
        appointments_in_watcher -= 1
        appointments_in_responder += 1
        sleep(1)

    # Test that they all show up in get_all_appointments at the correct stages.
    all_appointments = get_all_appointments()
    watching = all_appointments.get("watcher_appointments")
    responding = all_appointments.get("responder_trackers")
    assert len(watching) == appointments_in_watcher and len(responding) == appointments_in_responder
    responder_locators = [appointment["locator"] for uuid, appointment in responding.items()]
    assert set(responder_locators) == set(breached_appointments)

    new_addr = bitcoin_cli.getnewaddress()
    # Now let's mine some blocks so the appointment reaches its end. We need 100 + EXPIRY_DELTA -1
    bitcoin_cli.generatetoaddress(100 + teos_config.get("EXPIRY_DELTA") - 1, new_addr)

    # The appointment is no longer in the tower
    with pytest.raises(TowerResponseError):
        for appointment in appointments:
            get_appointment_info(appointment["locator"])


def test_appointment_malformed_penalty(bitcoin_cli):
    # Lets start by creating two valid transaction
    commitment_tx, penalty_tx = create_txs(bitcoin_cli)

    # Now we can modify the penalty so it is invalid when broadcast
    mod_penalty_tx = Tx.from_hex(penalty_tx)
    tx_in = mod_penalty_tx.tx_ins[0].copy(redeem_script=b"")
    mod_penalty_tx = mod_penalty_tx.copy(tx_ins=[tx_in])

    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(commitment_tx_id, mod_penalty_tx.hex())
    locator = compute_locator(commitment_tx_id)

    appointment = teos_cli.create_appointment(appointment_data)
    add_appointment(appointment)

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


def test_appointment_wrong_decryption_key(bitcoin_cli):
    # This tests an appointment encrypted with a key that has not been derived from the same source as the locator.
    # Therefore the tower won't be able to decrypt the blob once the appointment is triggered.
    commitment_tx, penalty_tx = create_txs(bitcoin_cli)

    # The appointment data is built using a random 32-byte value.
    appointment_data = build_appointment_data(get_random_value_hex(32), penalty_tx)

    # We cannot use teos_cli.add_appointment here since it computes the locator internally, so let's do it manually.
    # We will encrypt the blob using the random value and derive the locator from the commitment tx.
    appointment_data["locator"] = compute_locator(bitcoin_cli.decoderawtransaction(commitment_tx).get("txid"))
    appointment_data["encrypted_blob"] = Cryptographer.encrypt(penalty_tx, get_random_value_hex(32))
    appointment = Appointment.from_dict(appointment_data)

    signature = Cryptographer.sign(appointment.serialize(), user_sk)
    data = {"appointment": appointment.to_dict(), "signature": signature}

    # Send appointment to the server.
    response = teos_cli.post_request(data, teos_add_appointment_endpoint)
    response_json = teos_cli.process_post_response(response)

    # Check that the server has accepted the appointment
    tower_signature = response_json.get("signature")
    appointment_receipt = Appointment.create_receipt(signature, response_json.get("start_block"))
    rpk = Cryptographer.recover_pk(appointment_receipt, tower_signature)
    assert teos_id == Cryptographer.get_compressed_pk(rpk)
    assert response_json.get("locator") == appointment.locator

    # Trigger the appointment
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The appointment should have been removed since the decryption failed.
    with pytest.raises(TowerResponseError):
        get_appointment_info(appointment.locator)


def test_two_identical_appointments(bitcoin_cli):
    # Tests sending two identical appointments to the tower.
    # This tests sending an appointment with two valid transaction with the same locator.
    # If they come from the same user, the last one will be kept.
    commitment_tx, penalty_tx = create_txs(bitcoin_cli)
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")

    appointment_data = build_appointment_data(commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    # Send the appointment twice
    appointment = teos_cli.create_appointment(appointment_data)
    add_appointment(appointment)
    add_appointment(appointment)

    # Broadcast the commitment transaction and mine a block
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # The last appointment should have made it to the Responder
    appointment_info = get_appointment_info(locator)

    assert appointment_info.get("status") == "dispute_responded"
    assert appointment_info.get("appointment").get("penalty_rawtx") == penalty_tx


# FIXME: This test won't work since we're still passing appointment replicas to the Responder.
#        Uncomment when #88 is addressed
# def test_two_identical_appointments_different_users(bitcoin_cli):
#     # Tests sending two identical appointments from different users to the tower.
#     # This tests sending an appointment with two valid transaction with the same locator.
#     # If they come from different users, both will be kept, but one will be dropped fro double-spending when passing to
#     # the responder
#     commitment_tx, penalty_tx = create_txs(bitcoin_cli)
#     commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
#
#     appointment_data = build_appointment_data(commitment_tx_id, penalty_tx)
#     locator = compute_locator(commitment_tx_id)
#
#     # tmp keys from a different user
#     tmp_user_sk = PrivateKey()
#     tmp_user_id = hexlify(tmp_user_sk.public_key.format(compressed=True)).decode("utf-8")
#     teos_cli.register(tmp_user_id, teos_base_endpoint)
#
#     # Send the appointment twice
#     assert add_appointment(appointment_data) is True
#     assert add_appointment(appointment_data, sk=tmp_user_sk) is True
#
#     # Check that we can get it from both users
#     appointment_info = get_appointment_info(locator)
#     assert appointment_info.get("status") == "being_watched"
#     appointment_info = get_appointment_info(locator, sk=tmp_user_sk)
#     assert appointment_info.get("status") == "being_watched"
#
#     # Broadcast the commitment transaction and mine a block
#     new_addr = bitcoin_cli.getnewaddress()
#     broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)
#
#     # The last appointment should have made it to the Responder
#     sleep(1)
#     appointment_info = get_appointment_info(locator)
#     appointment_dup_info = get_appointment_info(locator, sk=tmp_user_sk)
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


def test_two_appointment_same_locator_different_penalty_different_users(bitcoin_cli):
    # This tests sending an appointment with two valid transaction with the same locator from different users
    commitment_tx, penalty_tx1 = create_txs(bitcoin_cli)
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")

    # We need to create a second penalty spending from the same commitment
    decoded_commitment_tx = bitcoin_cli.decoderawtransaction(commitment_tx)
    new_addr = bitcoin_cli.getnewaddress()
    penalty_tx2 = create_penalty_tx(bitcoin_cli, decoded_commitment_tx, new_addr)

    appointment1_data = build_appointment_data(commitment_tx_id, penalty_tx1)
    appointment2_data = build_appointment_data(commitment_tx_id, penalty_tx2)
    locator = compute_locator(commitment_tx_id)

    # tmp keys for a different user
    tmp_user_sk = PrivateKey()
    tmp_user_id = hexlify(tmp_user_sk.public_key.format(compressed=True)).decode("utf-8")
    teos_cli.register(tmp_user_id, teos_base_endpoint)

    appointment_1 = teos_cli.create_appointment(appointment1_data)
    add_appointment(appointment_1)
    appointment_2 = teos_cli.create_appointment(appointment2_data)
    add_appointment(appointment_2, sk=tmp_user_sk)

    # Broadcast the commitment transaction and mine a block
    new_addr = bitcoin_cli.getnewaddress()
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, new_addr)

    # One of the transactions must have made it to the Responder while the other must have been dropped for
    # double-spending. That means that one of the responses from the tower should fail
    appointment_info = None
    with pytest.raises(TowerResponseError):
        appointment_info = get_appointment_info(locator)
        appointment2_info = get_appointment_info(locator, sk=tmp_user_sk)

    if appointment_info is None:
        appointment_info = appointment2_info
        appointment1_data = appointment2_data

    assert appointment_info.get("status") == "dispute_responded"
    assert appointment_info.get("locator") == appointment1_data.get("locator")
    assert appointment_info.get("appointment").get("penalty_tx") == appointment1_data.get("penalty_tx")


def test_add_appointment_trigger_on_cache(bitcoin_cli):
    # This tests sending an appointment whose trigger is in the cache
    commitment_tx, penalty_tx = create_txs(bitcoin_cli)
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    # Let's send the commitment to the network and mine a block
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, bitcoin_cli.getnewaddress())

    # Send the data to the tower and request it back. It should have gone straightaway to the Responder
    appointment = teos_cli.create_appointment(appointment_data)
    add_appointment(appointment)
    assert get_appointment_info(locator).get("status") == "dispute_responded"


def test_add_appointment_invalid_trigger_on_cache(bitcoin_cli):
    # This tests sending an invalid appointment which trigger is in the cache
    commitment_tx, penalty_tx = create_txs(bitcoin_cli)
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")

    # We can just flip the justice tx so it is invalid
    appointment_data = build_appointment_data(commitment_tx_id, penalty_tx[::-1])
    locator = compute_locator(commitment_tx_id)

    # Let's send the commitment to the network and mine a block
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, bitcoin_cli.getnewaddress())
    sleep(1)

    # Send the data to the tower and request it back. It should get accepted but the data will be dropped.
    appointment = teos_cli.create_appointment(appointment_data)
    add_appointment(appointment)
    with pytest.raises(TowerResponseError):
        get_appointment_info(locator)


def test_add_appointment_trigger_on_cache_cannot_decrypt(bitcoin_cli):
    commitment_tx, penalty_tx = create_txs(bitcoin_cli)

    # Let's send the commitment to the network and mine a block
    broadcast_transaction_and_mine_block(bitcoin_cli, commitment_tx, bitcoin_cli.getnewaddress())
    sleep(1)

    # The appointment data is built using a random 32-byte value.
    appointment_data = build_appointment_data(get_random_value_hex(32), penalty_tx)

    # We cannot use teos_cli.add_appointment here since it computes the locator internally, so let's do it manually.
    appointment_data["locator"] = compute_locator(bitcoin_cli.decoderawtransaction(commitment_tx).get("txid"))
    appointment_data["encrypted_blob"] = Cryptographer.encrypt(penalty_tx, get_random_value_hex(32))
    appointment = Appointment.from_dict(appointment_data)

    signature = Cryptographer.sign(appointment.serialize(), user_sk)
    data = {"appointment": appointment.to_dict(), "signature": signature}

    # Send appointment to the server.
    response = teos_cli.post_request(data, teos_add_appointment_endpoint)
    response_json = teos_cli.process_post_response(response)

    # Check that the server has accepted the appointment
    tower_signature = response_json.get("signature")
    appointment_receipt = Appointment.create_receipt(signature, response_json.get("start_block"))
    rpk = Cryptographer.recover_pk(appointment_receipt, tower_signature)
    assert teos_id == Cryptographer.get_compressed_pk(rpk)
    assert response_json.get("locator") == appointment.locator

    # The appointment should should have been immediately dropped
    with pytest.raises(TowerResponseError):
        get_appointment_info(appointment_data["locator"])


def test_appointment_shutdown_teos_trigger_back_online(bitcoin_cli):
    # This tests data persistence. An appointment is sent to the tower, the tower is restarted and the appointment is
    # then triggered.
    global teosd_process

    teos_pid = teosd_process.pid

    commitment_tx, penalty_tx = create_txs(bitcoin_cli)
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    appointment = teos_cli.create_appointment(appointment_data)
    add_appointment(appointment)

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


def test_appointment_shutdown_teos_trigger_while_offline(bitcoin_cli):
    # This tests data persistence. An appointment is sent to the tower and the tower is stopped. The appointment is then
    # triggered with the tower offline, and then the tower is brought back online.
    global teosd_process

    teos_pid = teosd_process.pid

    commitment_tx, penalty_tx = create_txs(bitcoin_cli)
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    appointment_data = build_appointment_data(commitment_tx_id, penalty_tx)
    locator = compute_locator(commitment_tx_id)

    appointment = teos_cli.create_appointment(appointment_data)
    add_appointment(appointment)

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
