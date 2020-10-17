import pytest
import json
from time import sleep
from riemann.tx import Tx
from coincurve import PrivateKey

from contrib.client import teos_client

import common.receipts as receipts
from common.exceptions import TowerResponseError
from common.tools import compute_locator
from common.appointment import Appointment, AppointmentStatus
from common.cryptographer import Cryptographer

from teos.cli.teos_cli import RPCClient
from teos.utils.auth_proxy import JSONRPCException

from test.teos.conftest import (
    get_random_value_hex,
    create_txs,
    create_penalty_tx,
    bitcoin_cli,
    generate_block_with_transactions,
    generate_blocks,
    config,
)
from test.teos.e2e.conftest import build_appointment_data, run_teosd

teos_base_endpoint = "http://{}:{}".format(config.get("API_BIND"), config.get("API_PORT"))
teos_add_appointment_endpoint = "{}/add_appointment".format(teos_base_endpoint)
teos_get_appointment_endpoint = "{}/get_appointment".format(teos_base_endpoint)
teos_get_all_appointments_endpoint = "{}/get_all_appointments".format(teos_base_endpoint)
teos_get_subscription_info_endpoint = "{}/get_subscription_info".format(teos_base_endpoint)


user_sk = Cryptographer.generate_key()
user_id = Cryptographer.get_compressed_pk(user_sk.public_key)


appointments_in_watcher = 0
appointments_in_responder = 0


teosd_process, teos_id = None, None


def get_appointment_info(locator, sk=user_sk):
    sleep(1)  # Let's add a bit of delay so the state can be updated
    return teos_client.get_appointment(locator, sk, teos_id, teos_base_endpoint)


def add_appointment(appointment_data, sk=user_sk):
    return teos_client.add_appointment(appointment_data, sk, teos_id, teos_base_endpoint)


def get_subscription_info(sk=user_sk):
    return teos_client.get_subscription_info(sk, teos_id, teos_base_endpoint)


def test_commands_non_registered(run_bitcoind, teosd):
    # All commands should fail if the user is not registered
    global teosd_process, teos_id
    teosd_process, teos_id = teosd

    # Add appointment
    commitment_tx, commitment_tx_id, penalty_tx = create_txs()
    appointment_data = build_appointment_data(commitment_tx_id, penalty_tx)

    with pytest.raises(TowerResponseError):
        appointment = teos_client.create_appointment(appointment_data)
        add_appointment(appointment)

    # Get appointment
    with pytest.raises(TowerResponseError):
        assert get_appointment_info(appointment_data.get("locator"))

    # Get user's subscription info
    with pytest.raises(TowerResponseError):
        assert get_subscription_info()


def test_commands_registered(run_bitcoind):
    global appointments_in_watcher

    # Test registering and trying again
    teos_client.register(user_id, teos_id, teos_base_endpoint)

    # Add appointment
    commitment_tx, commitment_txid, penalty_tx = create_txs()
    appointment_data = build_appointment_data(commitment_txid, penalty_tx)

    appointment = teos_client.create_appointment(appointment_data)
    add_appointment(appointment)

    # Get appointment
    r = get_appointment_info(appointment_data.get("locator"))
    assert r.get("locator") == appointment.locator
    assert r.get("appointment") == appointment.to_dict()
    appointments_in_watcher += 1

    # Get subscription info
    r = get_subscription_info()
    assert r.get("appointments")[0] == appointment.locator


def test_appointment_life_cycle(run_bitcoind):
    global appointments_in_watcher, appointments_in_responder

    # First of all we need to register
    available_slots, subscription_expiry = teos_client.register(user_id, teos_id, teos_base_endpoint)

    # After that we can build an appointment and send it to the tower
    commitment_tx, commitment_txid, penalty_tx = create_txs()
    appointment_data = build_appointment_data(commitment_txid, penalty_tx)
    locator = compute_locator(commitment_txid)
    appointment = teos_client.create_appointment(appointment_data)
    add_appointment(appointment)
    appointments_in_watcher += 1

    # Get the information from the tower to check that it matches
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == AppointmentStatus.BEING_WATCHED
    assert appointment_info.get("locator") == locator
    assert appointment_info.get("appointment") == appointment.to_dict()

    rpc_client = RPCClient(config.get("RPC_BIND"), config.get("RPC_PORT"))

    # Check also the get_all_appointment endpoint
    all_appointments = json.loads(rpc_client.get_all_appointments())
    watching = all_appointments.get("watcher_appointments")
    responding = all_appointments.get("responder_trackers")
    assert len(watching) == appointments_in_watcher and len(responding) == 0

    # Trigger a breach and check again
    generate_block_with_transactions(commitment_tx)
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == AppointmentStatus.DISPUTE_RESPONDED
    assert appointment_info.get("locator") == locator
    appointments_in_watcher -= 1
    appointments_in_responder += 1

    all_appointments = json.loads(rpc_client.get_all_appointments())
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
    generate_blocks(100 + config.get("EXPIRY_DELTA") - 1)
    appointments_in_responder -= 1

    # The appointment is no longer in the tower
    with pytest.raises(TowerResponseError):
        get_appointment_info(locator)

    # Check that the appointment is not in the Gatekeeper by checking the available slots (should have increase by 1)
    # We can do so by topping up the subscription (FIXME: find a better way to check this).
    available_slots_response, _ = teos_client.register(user_id, teos_id, teos_base_endpoint)
    assert (
        available_slots_response
        == available_slots + config.get("SUBSCRIPTION_SLOTS") + 1 - appointments_in_watcher - appointments_in_responder
    )


def test_multiple_appointments_life_cycle(run_bitcoind):
    global appointments_in_watcher, appointments_in_responder
    # Tests that get_all_appointments returns all the appointments the tower is storing at various stages in the
    # appointment lifecycle.
    appointments = []

    txs = [create_txs() for _ in range(5)]

    # Create five appointments.
    for commitment_tx, commitment_txid, penalty_tx in txs:
        appointment_data = build_appointment_data(commitment_txid, penalty_tx)

        locator = compute_locator(commitment_txid)
        appointment = {
            "locator": locator,
            "commitment_tx": commitment_tx,
            "penalty_tx": penalty_tx,
            "appointment_data": appointment_data,
        }

        appointments.append(appointment)

    # Send all of them to watchtower.
    for appt in appointments:
        appointment = teos_client.create_appointment(appt.get("appointment_data"))
        add_appointment(appointment)
        appointments_in_watcher += 1

    # Two of these appointments are breached, and the watchtower responds to them.
    breached_appointments = []
    for i in range(2):
        generate_block_with_transactions(appointments[i]["commitment_tx"])
        breached_appointments.append(appointments[i]["locator"])
        appointments_in_watcher -= 1
        appointments_in_responder += 1
        sleep(1)

    # Test that they all show up in get_all_appointments at the correct stages.
    rpc_client = RPCClient(config.get("RPC_BIND"), config.get("RPC_PORT"))
    all_appointments = json.loads(rpc_client.get_all_appointments())
    watching = all_appointments.get("watcher_appointments")
    responding = all_appointments.get("responder_trackers")
    assert len(watching) == appointments_in_watcher and len(responding) == appointments_in_responder
    responder_locators = [appointment["locator"] for uuid, appointment in responding.items()]
    assert set(responder_locators) == set(breached_appointments)

    new_addr = bitcoin_cli.getnewaddress()
    # Now let's mine some blocks so the appointment reaches its end. We need 100 + EXPIRY_DELTA -1
    bitcoin_cli.generatetoaddress(100 + config.get("EXPIRY_DELTA") - 1, new_addr)

    # The appointment is no longer in the tower
    with pytest.raises(TowerResponseError):
        for appointment in appointments:
            get_appointment_info(appointment["locator"])


def test_appointment_malformed_penalty(run_bitcoind):
    # Lets start by creating two valid transaction
    commitment_tx, commitment_txid, penalty_tx = create_txs()

    # Now we can modify the penalty so it is invalid when broadcast (removing the witness should do)
    mod_penalty_tx = Tx.from_hex(penalty_tx).no_witness()

    appointment_data = build_appointment_data(commitment_txid, mod_penalty_tx.hex())
    locator = compute_locator(commitment_txid)

    appointment = teos_client.create_appointment(appointment_data)
    add_appointment(appointment)

    # Get the information from the tower to check that it matches
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == AppointmentStatus.BEING_WATCHED
    assert appointment_info.get("locator") == locator
    assert appointment_info.get("appointment") == appointment.to_dict()

    # Broadcast the commitment transaction and mine a block
    generate_block_with_transactions(commitment_tx)

    # The appointment should have been removed since the penalty_tx was malformed.
    with pytest.raises(TowerResponseError):
        get_appointment_info(locator)


def test_appointment_wrong_decryption_key(run_bitcoind):
    # This tests an appointment encrypted with a key that has not been derived from the same source as the locator.
    # Therefore the tower won't be able to decrypt the blob once the appointment is triggered.
    commitment_tx, _, penalty_tx = create_txs()

    # The appointment data is built using a random 32-byte value.
    appointment_data = build_appointment_data(get_random_value_hex(32), penalty_tx)

    # We cannot use teos_client.add_appointment here since it computes the locator internally, so let's do it manually.
    # We will encrypt the blob using the random value and derive the locator from the commitment tx.
    appointment_data["locator"] = compute_locator(bitcoin_cli.decoderawtransaction(commitment_tx).get("txid"))
    appointment_data["encrypted_blob"] = Cryptographer.encrypt(penalty_tx, get_random_value_hex(32))
    appointment = Appointment.from_dict(appointment_data)

    signature = Cryptographer.sign(appointment.serialize(), user_sk)
    data = {"appointment": appointment.to_dict(), "signature": signature}

    # Send appointment to the server.
    response = teos_client.post_request(data, teos_add_appointment_endpoint)
    response_json = teos_client.process_post_response(response)

    # Check that the server has accepted the appointment
    tower_signature = response_json.get("signature")
    appointment_receipt = receipts.create_appointment_receipt(signature, response_json.get("start_block"))
    rpk = Cryptographer.recover_pk(appointment_receipt, tower_signature)
    assert teos_id == Cryptographer.get_compressed_pk(rpk)
    assert response_json.get("locator") == appointment.locator

    # Trigger the appointment
    generate_block_with_transactions(commitment_tx)

    # The appointment should have been removed since the decryption failed.
    with pytest.raises(TowerResponseError):
        get_appointment_info(appointment.locator)


def test_two_identical_appointments(run_bitcoind):
    # Tests sending two identical appointments to the tower.
    # This tests sending an appointment with two valid transaction with the same locator.
    # If they come from the same user, the last one will be kept.
    commitment_tx, commitment_txid, penalty_tx = create_txs()

    appointment_data = build_appointment_data(commitment_txid, penalty_tx)
    locator = compute_locator(commitment_txid)

    # Send the appointment twice
    appointment = teos_client.create_appointment(appointment_data)
    add_appointment(appointment)
    add_appointment(appointment)

    # Broadcast the commitment transaction and mine a block
    generate_block_with_transactions(commitment_tx)

    # The last appointment should have made it to the Responder
    appointment_info = get_appointment_info(locator)

    assert appointment_info.get("status") == AppointmentStatus.DISPUTE_RESPONDED
    assert appointment_info.get("appointment").get("penalty_rawtx") == penalty_tx


# FIXME: This test won't work since we're still passing appointment replicas to the Responder.
#        Uncomment when #88 is addressed
# def test_two_identical_appointments_different_users(run_bitcoind):
#     # Tests sending two identical appointments from different users to the tower.
#     # This tests sending an appointment with two valid transaction with the same locator.
#     # If they come from different users, both will be kept, but one will be dropped fro double-spending when passing
#     to the responder
#     commitment_tx, commitment_txid, penalty_tx = create_txs()
#
#     appointment_data = build_appointment_data(commitment_txid, penalty_tx)
#     locator = compute_locator(commitment_txid)
#
#     # tmp keys from a different user
#     tmp_user_sk = PrivateKey()
#     tmp_user_id = Cryptographer.get_compressed_pk(tmp_user_sk.public_key)
#     teos_client.register(tmp_user_id, teos_base_endpoint)
#
#     # Send the appointment twice
#     assert add_appointment(appointment_data) is True
#     assert add_appointment(appointment_data, sk=tmp_user_sk) is True
#
#     # Check that we can get it from both users
#     appointment_info = get_appointment_info(locator)
#     assert appointment_info.get("status") == AppointmentStatus.BEING_WATCHED
#     appointment_info = get_appointment_info(locator, sk=tmp_user_sk)
#     assert appointment_info.get("status") == AppointmentStatus.BEING_WATCHED
#
#     # Broadcast the commitment transaction and mine a block
#     generate_block_with_transactions(commitment_tx)
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
#     assert appointment_info.get("status") == AppointmentStatus.DISPUTE_RESPONDED
#     assert appointment_info.get("appointment").get("penalty_rawtx") == penalty_tx


def test_two_appointment_same_locator_different_penalty_different_users(run_bitcoind):
    # This tests sending an appointment with two valid transaction with the same locator from different users
    commitment_tx, commitment_txid, penalty_tx1 = create_txs()

    # We need to create a second penalty spending from the same commitment
    decoded_commitment_tx = bitcoin_cli.decoderawtransaction(commitment_tx)
    new_addr = bitcoin_cli.getnewaddress()
    penalty_tx2 = create_penalty_tx(decoded_commitment_tx, new_addr)

    appointment1_data = build_appointment_data(commitment_txid, penalty_tx1)
    appointment2_data = build_appointment_data(commitment_txid, penalty_tx2)
    locator = compute_locator(commitment_txid)

    # tmp keys for a different user
    tmp_user_sk = PrivateKey()
    tmp_user_id = Cryptographer.get_compressed_pk(tmp_user_sk.public_key)
    teos_client.register(tmp_user_id, teos_id, teos_base_endpoint)

    appointment_1 = teos_client.create_appointment(appointment1_data)
    add_appointment(appointment_1)
    appointment_2 = teos_client.create_appointment(appointment2_data)
    add_appointment(appointment_2, sk=tmp_user_sk)

    # Broadcast the commitment transaction and mine a block
    generate_block_with_transactions(commitment_tx)

    # One of the transactions must have made it to the Responder while the other must have been dropped for
    # double-spending. That means that one of the responses from the tower should fail
    appointment_info = None
    with pytest.raises(TowerResponseError):
        appointment_info = get_appointment_info(locator)
        appointment2_info = get_appointment_info(locator, sk=tmp_user_sk)

    if appointment_info is None:
        appointment_info = appointment2_info
        appointment1_data = appointment2_data

    assert appointment_info.get("status") == AppointmentStatus.DISPUTE_RESPONDED
    assert appointment_info.get("locator") == appointment1_data.get("locator")
    assert appointment_info.get("appointment").get("penalty_tx") == appointment1_data.get("penalty_tx")


def test_add_appointment_trigger_on_cache(run_bitcoind):
    # This tests sending an appointment whose trigger is in the cache
    commitment_tx, commitment_txid, penalty_tx = create_txs()
    appointment_data = build_appointment_data(commitment_txid, penalty_tx)
    locator = compute_locator(commitment_txid)

    # Let's send the commitment to the network and mine a block
    generate_block_with_transactions(commitment_tx)

    # Send the data to the tower and request it back. It should have gone straightaway to the Responder
    appointment = teos_client.create_appointment(appointment_data)
    add_appointment(appointment)
    assert get_appointment_info(locator).get("status") == AppointmentStatus.DISPUTE_RESPONDED


def test_add_appointment_invalid_trigger_on_cache(run_bitcoind):
    # This tests sending an invalid appointment which trigger is in the cache
    commitment_tx, commitment_txid, penalty_tx = create_txs()

    # We can just flip the justice tx so it is invalid
    appointment_data = build_appointment_data(commitment_txid, penalty_tx[::-1])
    locator = compute_locator(commitment_txid)

    # Let's send the commitment to the network and mine a block
    generate_block_with_transactions(commitment_tx)
    sleep(1)

    # Send the data to the tower and request it back. It should get accepted but the data will be dropped.
    appointment = teos_client.create_appointment(appointment_data)
    add_appointment(appointment)
    with pytest.raises(TowerResponseError):
        get_appointment_info(locator)


def test_add_appointment_trigger_on_cache_cannot_decrypt(run_bitcoind):
    commitment_tx, _, penalty_tx = create_txs()

    # Let's send the commitment to the network and mine a block
    generate_block_with_transactions(commitment_tx)
    sleep(1)

    # The appointment data is built using a random 32-byte value.
    appointment_data = build_appointment_data(get_random_value_hex(32), penalty_tx)

    # We cannot use teos_client.add_appointment here since it computes the locator internally, so let's do it manually.
    appointment_data["locator"] = compute_locator(bitcoin_cli.decoderawtransaction(commitment_tx).get("txid"))
    appointment_data["encrypted_blob"] = Cryptographer.encrypt(penalty_tx, get_random_value_hex(32))
    appointment = Appointment.from_dict(appointment_data)

    signature = Cryptographer.sign(appointment.serialize(), user_sk)
    data = {"appointment": appointment.to_dict(), "signature": signature}

    # Send appointment to the server.
    response = teos_client.post_request(data, teos_add_appointment_endpoint)
    response_json = teos_client.process_post_response(response)

    # Check that the server has accepted the appointment
    tower_signature = response_json.get("signature")
    appointment_receipt = receipts.create_appointment_receipt(signature, response_json.get("start_block"))
    rpk = Cryptographer.recover_pk(appointment_receipt, tower_signature)
    assert teos_id == Cryptographer.get_compressed_pk(rpk)
    assert response_json.get("locator") == appointment.locator

    # The appointment should should have been immediately dropped
    with pytest.raises(TowerResponseError):
        get_appointment_info(appointment_data["locator"])


def test_appointment_shutdown_teos_trigger_back_online(run_bitcoind):
    global teosd_process
    # This tests data persistence. An appointment is sent to the tower, the tower is restarted and the appointment is
    # then triggered.
    teos_pid = teosd_process.pid

    commitment_tx, commitment_txid, penalty_tx = create_txs()
    appointment_data = build_appointment_data(commitment_txid, penalty_tx)
    locator = compute_locator(commitment_txid)

    appointment = teos_client.create_appointment(appointment_data)
    add_appointment(appointment)

    # Restart teos
    rpc_client = RPCClient(config.get("RPC_BIND"), config.get("RPC_PORT"))
    rpc_client.stop()
    teosd_process.join()

    teosd_process, _ = run_teosd()

    assert teos_pid != teosd_process.pid

    # Check that the appointment is still in the Watcher
    appointment_info = get_appointment_info(locator)

    assert appointment_info.get("status") == AppointmentStatus.BEING_WATCHED
    assert appointment_info.get("appointment") == appointment.to_dict()

    # Trigger appointment after restart
    generate_block_with_transactions(commitment_tx)

    # The appointment should have been moved to the Responder
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == AppointmentStatus.DISPUTE_RESPONDED


def test_appointment_shutdown_teos_trigger_while_offline(run_bitcoind):
    global teosd_process
    # This tests data persistence. An appointment is sent to the tower and the tower is stopped. The appointment is then
    # triggered with the tower offline, and then the tower is brought back online.
    teos_pid = teosd_process.pid

    commitment_tx, commitment_txid, penalty_tx = create_txs()
    appointment_data = build_appointment_data(commitment_txid, penalty_tx)
    locator = compute_locator(commitment_txid)

    appointment = teos_client.create_appointment(appointment_data)
    add_appointment(appointment)

    # Check that the appointment is still in the Watcher
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == AppointmentStatus.BEING_WATCHED
    assert appointment_info.get("appointment") == appointment.to_dict()

    # Shutdown and trigger
    rpc_client = RPCClient(config.get("RPC_BIND"), config.get("RPC_PORT"))
    rpc_client.stop()
    teosd_process.join()

    generate_block_with_transactions(commitment_tx)

    # Restart
    teosd_process, _ = run_teosd()
    assert teos_pid != teosd_process.pid

    # The appointment should have been moved to the Responder
    appointment_info = get_appointment_info(locator)
    assert appointment_info.get("status") == AppointmentStatus.DISPUTE_RESPONDED
