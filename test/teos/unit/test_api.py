import pytest
from binascii import hexlify

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
from common.cryptographer import Cryptographer, hash_160
from common.constants import (
    HTTP_OK,
    HTTP_NOT_FOUND,
    HTTP_BAD_REQUEST,
    HTTP_SERVICE_UNAVAILABLE,
    LOCATOR_LEN_BYTES,
    ENCRYPTED_BLOB_MAX_SIZE_HEX,
)


TEOS_API = "http://{}:{}".format(HOST, PORT)
register_endpoint = "{}/register".format(TEOS_API)
add_appointment_endpoint = "{}/add_appointment".format(TEOS_API)
get_appointment_endpoint = "{}/get_appointment".format(TEOS_API)
get_all_appointment_endpoint = "{}/get_all_appointments".format(TEOS_API)

# Reduce the maximum number of appointments to something we can test faster
MAX_APPOINTMENTS = 100
MULTIPLE_APPOINTMENTS = 10

TWO_SLOTS_BLOTS = "A" * ENCRYPTED_BLOB_MAX_SIZE_HEX + "AA"

appointments = {}
locator_dispute_tx_map = {}

config = get_config()


client_sk, client_pk = generate_keypair()
compressed_client_pk = hexlify(client_pk.format(compressed=True)).decode("utf-8")


@pytest.fixture(scope="module", autouse=True)
def api(db_manager, carrier, block_processor, run_bitcoind):

    sk, pk = generate_keypair()

    responder = Responder(db_manager, carrier, block_processor)
    watcher = Watcher(db_manager, block_processor, responder, sk.to_der(), MAX_APPOINTMENTS, config.get("EXPIRY_DELTA"))

    chain_monitor = ChainMonitor(
        watcher.block_queue, watcher.responder.block_queue, block_processor, bitcoind_feed_params
    )
    watcher.awake()
    chain_monitor.monitor_chain()

    gatekeeper = Gatekeeper(config.get("DEFAULT_SLOTS"))
    api = API(Inspector(block_processor, config.get("MIN_TO_SELF_DELAY")), watcher, gatekeeper)

    return api


@pytest.fixture()
def app(api):
    with api.app.app_context():
        yield api.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def appointment():
    appointment, dispute_tx = generate_dummy_appointment()
    locator_dispute_tx_map[appointment.locator] = dispute_tx

    return appointment


def add_appointment(client, appointment_data, user_pk):
    r = client.post(add_appointment_endpoint, json=appointment_data)

    if r.status_code == HTTP_OK:
        locator = appointment_data.get("appointment").get("locator")
        uuid = hash_160("{}{}".format(locator, user_pk))
        appointments[uuid] = appointment_data["appointment"]

    return r


def test_register(client):
    data = {"public_key": compressed_client_pk}
    r = client.post(register_endpoint, json=data)
    assert r.status_code == HTTP_OK
    assert r.json.get("public_key") == compressed_client_pk
    assert r.json.get("available_slots") == config.get("DEFAULT_SLOTS")


def test_register_top_up(client):
    # Calling register more than once will give us DEFAULT_SLOTS * number_of_calls slots
    temp_sk, tmp_pk = generate_keypair()
    tmp_pk_hex = hexlify(tmp_pk.format(compressed=True)).decode("utf-8")

    data = {"public_key": tmp_pk_hex}

    for i in range(10):
        r = client.post(register_endpoint, json=data)
        assert r.status_code == HTTP_OK
        assert r.json.get("public_key") == tmp_pk_hex
        assert r.json.get("available_slots") == config.get("DEFAULT_SLOTS") * (i + 1)


def test_register_no_client_pk(client):
    data = {"public_key": compressed_client_pk + compressed_client_pk}
    r = client.post(register_endpoint, json=data)
    assert r.status_code == HTTP_BAD_REQUEST


def test_register_wrong_client_pk(client):
    data = {}
    r = client.post(register_endpoint, json=data)
    assert r.status_code == HTTP_BAD_REQUEST


def test_register_no_json(client):
    r = client.post(register_endpoint, data="random_message")
    assert r.status_code == HTTP_BAD_REQUEST


def test_register_json_no_inner_dict(client):
    r = client.post(register_endpoint, json="random_message")
    assert r.status_code == HTTP_BAD_REQUEST


def test_add_appointment(api, client, appointment):
    # Simulate the user registration
    api.gatekeeper.registered_users[compressed_client_pk] = 1

    # Properly formatted appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_OK
    assert r.json.get("available_slots") == 0


def test_add_appointment_no_json(api, client, appointment):
    # Simulate the user registration
    api.gatekeeper.registered_users[compressed_client_pk] = 1

    # Properly formatted appointment
    r = client.post(add_appointment_endpoint, data="random_message")
    assert r.status_code == HTTP_BAD_REQUEST


def test_add_appointment_json_no_inner_dict(api, client, appointment):
    # Simulate the user registration
    api.gatekeeper.registered_users[compressed_client_pk] = 1

    # Properly formatted appointment
    r = client.post(add_appointment_endpoint, json="random_message")
    assert r.status_code == HTTP_BAD_REQUEST


def test_add_appointment_wrong(api, client, appointment):
    # Simulate the user registration
    api.gatekeeper.registered_users[compressed_client_pk] = 1

    # Incorrect appointment
    appointment.to_self_delay = 0
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Error {}:".format(errors.APPOINTMENT_FIELD_TOO_SMALL) in r.json.get("error")


def test_add_appointment_not_registered(api, client, appointment):
    # Properly formatted appointment
    tmp_sk, tmp_pk = generate_keypair()
    tmp_compressed_pk = hexlify(tmp_pk.format(compressed=True)).decode("utf-8")

    appointment_signature = Cryptographer.sign(appointment.serialize(), tmp_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, tmp_compressed_pk
    )
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Error {}:".format(errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS) in r.json.get("error")


def test_add_appointment_registered_no_free_slots(api, client, appointment):
    # Empty the user slots
    api.gatekeeper.registered_users[compressed_client_pk] = 0

    # Properly formatted appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Error {}:".format(errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS) in r.json.get("error")


def test_add_appointment_registered_not_enough_free_slots(api, client, appointment):
    # Give some slots to the user
    api.gatekeeper.registered_users[compressed_client_pk] = 1

    # Properly formatted appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)

    # Let's create a big blob
    appointment.encrypted_blob.data = TWO_SLOTS_BLOTS

    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Error {}:".format(errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS) in r.json.get("error")


def test_add_appointment_multiple_times_same_user(api, client, appointment, n=MULTIPLE_APPOINTMENTS):
    # Multiple appointments with the same locator should be valid and counted as updates
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)

    # Simulate registering enough slots
    api.gatekeeper.registered_users[compressed_client_pk] = n
    for _ in range(n):
        r = add_appointment(
            client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
        )
        assert r.status_code == HTTP_OK
        assert r.json.get("available_slots") == n - 1

    # Since all updates came from the same user, only the last one is stored
    assert len(api.watcher.locator_uuid_map[appointment.locator]) == 1


def test_add_appointment_multiple_times_different_users(api, client, appointment, n=MULTIPLE_APPOINTMENTS):
    # Create user keys and appointment signatures
    user_keys = [generate_keypair() for _ in range(n)]
    signatures = [Cryptographer.sign(appointment.serialize(), key[0]) for key in user_keys]
    compressed_pks = [hexlify(pk.format(compressed=True)).decode("utf-8") for sk, pk in user_keys]

    # Add one slot per public key
    for pair in user_keys:
        api.gatekeeper.registered_users[hexlify(pair[1].format(compressed=True)).decode("utf-8")] = 2

    # Send the appointments
    for compressed_pk, signature in zip(compressed_pks, signatures):
        r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": signature}, compressed_pk)
        assert r.status_code == HTTP_OK
        assert r.json.get("available_slots") == 1

    # Check that all the appointments have been added and that there are no duplicates
    assert len(set(api.watcher.locator_uuid_map[appointment.locator])) == n


def test_get_appointment_no_json(api, client, appointment):
    r = client.post(add_appointment_endpoint, data="random_message")
    assert r.status_code == HTTP_BAD_REQUEST


def test_get_appointment_json_no_inner_dict(api, client, appointment):
    r = client.post(add_appointment_endpoint, json="random_message")
    assert r.status_code == HTTP_BAD_REQUEST


def test_request_random_appointment_registered_user(client, user_sk=client_sk):
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    message = "get appointment {}".format(locator)
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    data = {"locator": locator, "signature": signature}
    r = client.post(get_appointment_endpoint, json=data)

    # We should get a 404 not found since we are using a made up locator
    received_appointment = r.json
    assert r.status_code == HTTP_NOT_FOUND
    assert received_appointment.get("status") == "not_found"


def test_request_appointment_not_registered_user(client):
    # Not registered users have no associated appointments, so this should fail
    tmp_sk, tmp_pk = generate_keypair()

    # The tower is designed so a not found appointment and a request from a non-registered user return the same error to
    # prevent proving.
    test_request_random_appointment_registered_user(client, tmp_sk)


def test_request_appointment_in_watcher(api, client, appointment):
    # Give slots to the user
    api.gatekeeper.registered_users[compressed_client_pk] = 1

    # Add an appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_OK

    message = "get appointment {}".format(appointment.locator)
    signature = Cryptographer.sign(message.encode("utf-8"), client_sk)
    data = {"locator": appointment.locator, "signature": signature}

    # Next we can request it
    r = client.post(get_appointment_endpoint, json=data)
    assert r.status_code == HTTP_OK

    # Check that the appointment is on the watcher
    assert r.json.get("status") == "being_watched"

    # Check the the sent appointment matches the received one
    assert r.json.get("locator") == appointment.locator
    assert appointment.to_dict() == r.json.get("appointment")


def test_request_appointment_in_responder(api, client, appointment):
    # Give slots to the user
    api.gatekeeper.registered_users[compressed_client_pk] = 1

    # Let's do something similar to what we did with the watcher but now we'll send the dispute tx to the network
    dispute_tx = locator_dispute_tx_map.pop(appointment.locator)
    bitcoin_cli(bitcoind_connect_params).sendrawtransaction(dispute_tx)

    # Add an appointment (avoid calling add_appointment to not add this one to the sent appointments list)
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = client.post(
        add_appointment_endpoint, json={"appointment": appointment.to_dict(), "signature": appointment_signature}
    )
    assert r.status_code == HTTP_OK

    # Generate a block to trigger the watcher
    generate_block()

    # Request back the data
    message = "get appointment {}".format(appointment.locator)
    signature = Cryptographer.sign(message.encode("utf-8"), client_sk)
    data = {"locator": appointment.locator, "signature": signature}

    # Next we can request it
    r = client.post(get_appointment_endpoint, json=data)
    assert r.status_code == HTTP_OK

    # Check that the appointment is on the watcher
    assert r.json.get("status") == "dispute_responded"

    # Check the the sent appointment matches the received one
    assert appointment.locator == r.json.get("locator")
    assert appointment.encrypted_blob.data == Cryptographer.encrypt(
        Blob(r.json.get("appointment").get("penalty_rawtx")), r.json.get("appointment").get("dispute_txid")
    )

    # Delete appointment so it does not mess up with future tests
    uuids = api.watcher.responder.tx_tracker_map.pop(r.json.get("appointment").get("penalty_txid"))
    api.watcher.responder.db_manager.delete_responder_tracker(uuids[0])


def test_get_all_appointments_watcher(client):
    r = client.get(get_all_appointment_endpoint)
    assert r.status_code == HTTP_OK

    received_appointments = r.json

    # Make sure there all the locators re in the watcher
    watcher_locators = [v["locator"] for k, v in received_appointments["watcher_appointments"].items()]
    local_locators = [appointment["locator"] for uuid, appointment in appointments.items()]

    assert set(watcher_locators) == set(local_locators)
    assert len(received_appointments["responder_trackers"]) == 0


def test_get_all_appointments_responder(api, client):
    # Trigger all disputes
    local_locators = [appointment.get("locator") for uuids, appointment in appointments.items()]
    for locator, dispute_tx in locator_dispute_tx_map.items():
        if locator in local_locators:
            bitcoin_cli(bitcoind_connect_params).sendrawtransaction(dispute_tx)

    # Confirm transactions
    generate_blocks(6)

    # Get all appointments
    r = client.get(get_all_appointment_endpoint)
    received_appointments = r.json

    # Make sure there is not pending locator in the watcher
    responder_trackers = [v["locator"] for k, v in received_appointments["responder_trackers"].items()]

    assert set(responder_trackers) == set(local_locators)
    assert len(received_appointments["watcher_appointments"]) == 0


# UPDATE TEST MUST BE AFTER get_all_appointments TESTS:
# This tests send data to the Watcher and Responder that may not be passed along, so it's easier to have it here and
# not keep track of what's being sent
def test_add_appointment_update_same_size(api, client, appointment):
    # Update an appointment by one of the same size and check that no additional slots are filled
    api.gatekeeper.registered_users[compressed_client_pk] = 1

    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    # # Since we will replace the appointment, we won't added to appointments
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0

    # The user has no additional slots, but it should be able to update
    # Let's just reverse the encrypted blob for example
    appointment.encrypted_blob.data = appointment.encrypted_blob.data[::-1]
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0


def test_add_appointment_update_bigger(api, client, appointment):
    # Update an appointment by one bigger, and check additional slots are filled
    api.gatekeeper.registered_users[compressed_client_pk] = 2

    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 1

    # The user has one slot, so it should be able to update as long as it only takes 1 additional slot
    appointment.encrypted_blob.data = TWO_SLOTS_BLOTS
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0

    # Check that it'll fail if no enough slots are available
    # Double the size from before
    appointment.encrypted_blob.data = TWO_SLOTS_BLOTS + TWO_SLOTS_BLOTS
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_BAD_REQUEST


def test_add_appointment_update_smaller(api, client, appointment):
    # Update an appointment by one bigger, and check slots are freed
    api.gatekeeper.registered_users[compressed_client_pk] = 2

    # This should take 2 slots
    appointment.encrypted_blob.data = TWO_SLOTS_BLOTS
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0

    # Let's update with one just small enough
    appointment.encrypted_blob.data = "A" * (ENCRYPTED_BLOB_MAX_SIZE_HEX - 2)
    appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
    )
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 1


def test_add_too_many_appointment(api, client):
    # Give slots to the user
    api.gatekeeper.registered_users[compressed_client_pk] = 200

    free_appointment_slots = MAX_APPOINTMENTS - len(api.watcher.appointments)

    for i in range(free_appointment_slots + 1):
        appointment, dispute_tx = generate_dummy_appointment()
        locator_dispute_tx_map[appointment.locator] = dispute_tx

        appointment_signature = Cryptographer.sign(appointment.serialize(), client_sk)
        r = add_appointment(
            client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, compressed_client_pk
        )

        if i < free_appointment_slots:
            assert r.status_code == HTTP_OK
        else:
            assert r.status_code == HTTP_SERVICE_UNAVAILABLE
