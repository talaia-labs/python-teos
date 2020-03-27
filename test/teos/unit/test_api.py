import json
import pytest
import requests
from time import sleep
from binascii import hexlify
from threading import Thread

from teos.api import API
from teos import HOST, PORT
import teos.errors as errors
from teos.watcher import Watcher
from teos.tools import bitcoin_cli
from teos.inspector import Inspector
from teos.responder import Responder
from teos.gatekeeper import Gatekeeper
from teos.chain_monitor import ChainMonitor

from test.teos.unit.conftest import (
    generate_block,
    generate_blocks,
    get_random_value_hex,
    generate_dummy_appointment,
    generate_keypair,
    get_config,
    bitcoind_connect_params,
    bitcoind_feed_params,
)

from common.blob import Blob
from common.cryptographer import Cryptographer
from common.constants import HTTP_OK, HTTP_NOT_FOUND, HTTP_BAD_REQUEST, HTTP_SERVICE_UNAVAILABLE, LOCATOR_LEN_BYTES


TEOS_API = "http://{}:{}".format(HOST, PORT)
add_appointment_endpoint = "{}/add_appointment".format(TEOS_API)
get_appointment_endpoint = "{}/get_appointment".format(TEOS_API)
get_all_appointment_endpoint = "{}/get_all_appointments".format(TEOS_API)

MULTIPLE_APPOINTMENTS = 10

appointments = []
locator_dispute_tx_map = {}

config = get_config()


client_sk, client_pk = generate_keypair()
client_pk_hex = hexlify(client_pk.format(compressed=True)).decode("utf-8")


@pytest.fixture(scope="module")
def api(db_manager, carrier, block_processor):
    sk, pk = generate_keypair()

    responder = Responder(db_manager, carrier, block_processor)
    watcher = Watcher(
        db_manager, block_processor, responder, sk.to_der(), config.get("MAX_APPOINTMENTS"), config.get("EXPIRY_DELTA")
    )

    chain_monitor = ChainMonitor(
        watcher.block_queue, watcher.responder.block_queue, block_processor, bitcoind_feed_params
    )
    watcher.awake()
    chain_monitor.monitor_chain()

    api = API(Inspector(block_processor, config.get("MIN_TO_SELF_DELAY")), watcher, Gatekeeper())
    api_thread = Thread(target=api.start)
    api_thread.daemon = True
    api_thread.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)

    return api


@pytest.fixture
def appointment():
    appointment, dispute_tx = generate_dummy_appointment()
    locator_dispute_tx_map[appointment.locator] = dispute_tx

    return appointment


def add_appointment(appointment_data):
    r = requests.post(url=add_appointment_endpoint, json=appointment_data, timeout=5)

    if r.status_code == HTTP_OK:
        appointments.append(appointment_data["appointment"])

    return r


def test_add_appointment(api, run_bitcoind, appointment):
    # Simulate the user registration
    api.gatekeeper.registered_users[client_pk_hex] = 1

    # Properly formatted appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment({"appointment": appointment.to_dict(), "signature": appointment_signature})
    assert r.status_code == HTTP_OK


def test_add_appointment_wrong(api, appointment):
    # Simulate the user registration
    api.gatekeeper.registered_users[client_pk_hex] = 1

    # Incorrect appointment
    appointment.to_self_delay = 0
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment({"appointment": appointment.to_dict(), "signature": appointment_signature})
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Error {}:".format(errors.APPOINTMENT_FIELD_TOO_SMALL) in r.json().get("error")


def test_add_appointment_not_registered(api, appointment):
    # Properly formatted appointment
    tmp_sk, tmp_pk = generate_keypair()
    appointment_signature = Cryptographer.sign(appointment.serialize(), tmp_sk)
    r = add_appointment({"appointment": appointment.to_dict(), "signature": appointment_signature})
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Error {}:".format(errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS) in r.json().get("error")


def test_add_appointment_registered_no_free_slots(api, appointment):
    # Empty the user slots
    api.gatekeeper.registered_users[client_pk_hex] = 0

    # Properly formatted appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment({"appointment": appointment.to_dict(), "signature": appointment_signature})
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Error {}:".format(errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS) in r.json().get("error")


def test_add_appointment_registered_not_enough_free_slots(api, appointment):
    # Empty the user slots
    api.gatekeeper.registered_users[client_pk_hex] = 1

    # Properly formatted appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)

    # Let's create a big blob
    for _ in range(10):
        appointment.encrypted_blob.data += appointment.encrypted_blob.data

    r = add_appointment({"appointment": appointment.to_dict(), "signature": appointment_signature})
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Error {}:".format(errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS) in r.json().get("error")


def test_add_appointment_multiple_times_same_user(api, appointment, n=MULTIPLE_APPOINTMENTS):
    # Multiple appointments with the same locator should be valid
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)

    # Simulate registering enough slots
    api.gatekeeper.registered_users[client_pk_hex] = n
    # DISCUSS: #34-store-identical-appointments
    for _ in range(n):
        r = add_appointment({"appointment": appointment.to_dict(), "signature": appointment_signature})
        assert r.status_code == HTTP_OK

    # Since all updates came from the same user, only the last one is stored
    assert len(api.watcher.locator_uuid_map[appointment.locator]) == 1


def test_add_appointment_multiple_times_different_users(api, appointment, n=MULTIPLE_APPOINTMENTS):
    # Create user keys and appointment signatures
    user_keys = [generate_keypair() for _ in range(n)]
    signatures = [Cryptographer.sign(appointment.serialize(), key[0]) for key in user_keys]

    # Add one slot per public key
    for pair in user_keys:
        api.gatekeeper.registered_users[hexlify(pair[1].format(compressed=True)).decode("utf-8")] = 1

    # Send the appointments
    for signature in signatures:
        r = add_appointment({"appointment": appointment.to_dict(), "signature": signature})
        assert r.status_code == HTTP_OK

    # Check that all the appointments have been added and that there are no duplicates
    assert len(set(api.watcher.locator_uuid_map[appointment.locator])) == n


def test_request_random_appointment_registered_user(user_sk=client_sk):
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    message = "get appointment {}".format(locator)
    signature = Cryptographer.sign(message.encode("utf-8"), client_sk)

    data = {"locator": locator, "signature": signature}
    r = requests.post(url=get_appointment_endpoint, json=data, timeout=5)

    # We should get a 404 not found since we are using a made up locator
    received_appointment = r.json()
    assert r.status_code == HTTP_NOT_FOUND
    assert received_appointment.get("status") == "not_found"


def test_request_appointment_not_registered_user():
    # Not registered users have no associated appointments, so this should fail
    tmp_sk, tmp_pk = generate_keypair()

    # The tower is designed so a not found appointment and a request from a non-registered user return the same error to
    # prevent proving.
    test_request_random_appointment_registered_user(tmp_sk)


def test_request_appointment_in_watcher(api, appointment):
    # Give slots to the user
    api.gatekeeper.registered_users[client_pk_hex] = 1

    # Add an appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment({"appointment": appointment.to_dict(), "signature": appointment_signature})
    assert r.status_code == HTTP_OK

    message = "get appointment {}".format(appointment.locator)
    signature = Cryptographer.sign(message.encode("utf-8"), client_sk)
    data = {"locator": appointment.locator, "signature": signature}

    # Next we can request it
    r = requests.post(url=get_appointment_endpoint, json=data, timeout=5)
    assert r.status_code == HTTP_OK

    appointment_data = json.loads(r.content)
    # Check that the appointment is on the watcher
    status = appointment_data.pop("status")
    assert status == "being_watched"

    # Check the the sent appointment matches the received one
    assert appointment.to_dict() == appointment_data


def test_request_appointment_in_responder(api, appointment):
    # Give slots to the user
    api.gatekeeper.registered_users[client_pk_hex] = 1

    # Let's do something similar to what we did with the watcher but now we'll send the dispute tx to the network
    dispute_tx = locator_dispute_tx_map.pop(appointment.locator)
    bitcoin_cli(bitcoind_connect_params).sendrawtransaction(dispute_tx)

    # Add an appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment({"appointment": appointment.to_dict(), "signature": appointment_signature})
    assert r.status_code == HTTP_OK

    # Generate a block to trigger the watcher
    generate_block()

    # Request back the data
    message = "get appointment {}".format(appointment.locator)
    signature = Cryptographer.sign(message.encode("utf-8"), client_sk)
    data = {"locator": appointment.locator, "signature": signature}

    # Next we can request it
    r = requests.post(url=get_appointment_endpoint, json=data, timeout=5)
    assert r.status_code == HTTP_OK

    appointment_data = json.loads(r.content)
    # Check that the appointment is on the watcher
    status = appointment_data.pop("status")
    assert status == "dispute_responded"

    # Check the the sent appointment matches the received one
    assert appointment.locator == appointment_data.get("locator")
    assert appointment.encrypted_blob.data == Cryptographer.encrypt(
        Blob(appointment_data.get("penalty_rawtx")), appointment_data.get("dispute_txid")
    )

    # Delete appointment so it does not mess up with future tests
    appointments.pop()
    uuids = api.watcher.responder.tx_tracker_map.pop(appointment_data.get("penalty_txid"))
    api.watcher.responder.db_manager.delete_responder_tracker(uuids[0])
    # api.watcher.responder.trackers.pop(uuids[0])


def test_get_all_appointments_watcher():
    r = requests.get(url=get_all_appointment_endpoint)
    assert r.status_code == HTTP_OK

    received_appointments = json.loads(r.content)

    # Make sure there all the locators re in the watcher
    watcher_locators = [v["locator"] for k, v in received_appointments["watcher_appointments"].items()]
    local_locators = [appointment["locator"] for appointment in appointments]

    assert set(watcher_locators) == set(local_locators)
    assert len(received_appointments["responder_trackers"]) == 0


def test_get_all_appointments_responder():
    # Trigger all disputes
    locators = [appointment["locator"] for appointment in appointments]
    for locator, dispute_tx in locator_dispute_tx_map.items():
        if locator in locators:
            bitcoin_cli(bitcoind_connect_params).sendrawtransaction(dispute_tx)

    # Confirm transactions
    generate_blocks(6)

    # Get all appointments
    r = requests.get(url=get_all_appointment_endpoint)
    received_appointments = json.loads(r.content)

    # Make sure there is not pending locator in the watcher
    responder_trackers = [v["locator"] for k, v in received_appointments["responder_trackers"].items()]
    local_locators = [appointment["locator"] for appointment in appointments]

    assert set(responder_trackers) == set(local_locators)
    assert len(received_appointments["watcher_appointments"]) == 0


def test_add_too_many_appointment(api):
    # Give slots to the user
    api.gatekeeper.registered_users[client_pk_hex] = 100

    for i in range(config.get("MAX_APPOINTMENTS") - len(appointments)):
        appointment, dispute_tx = generate_dummy_appointment()
        locator_dispute_tx_map[appointment.locator] = dispute_tx

        appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
        r = add_appointment({"appointment": appointment.to_dict(), "signature": appointment_signature})

        if i != config.get("MAX_APPOINTMENTS") - len(appointments):
            assert r.status_code == HTTP_OK
        else:
            assert r.status_code == HTTP_SERVICE_UNAVAILABLE
