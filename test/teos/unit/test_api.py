import pytest
from shutil import rmtree
from binascii import hexlify

from teos.api import API
import common.errors as errors
from teos.inspector import Inspector
from teos.gatekeeper import UserInfo
from teos.appointments_dbm import AppointmentsDBM
from teos.responder import Responder, TransactionTracker
from teos.extended_appointment import ExtendedAppointment
from teos.watcher import Watcher, AppointmentAlreadyTriggered

from test.teos.unit.conftest import (
    get_random_value_hex,
    generate_dummy_appointment,
    generate_keypair,
    get_config,
    create_dummy_transaction,
    compute_locator,
)

from common.cryptographer import Cryptographer, hash_160
from common.constants import (
    HTTP_OK,
    HTTP_NOT_FOUND,
    HTTP_BAD_REQUEST,
    HTTP_SERVICE_UNAVAILABLE,
    LOCATOR_LEN_BYTES,
    ENCRYPTED_BLOB_MAX_SIZE_HEX,
)

config = get_config()

TEOS_API = "http://{}:{}".format(config.get("API_HOST"), config.get("API_PORT"))
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


user_sk, user_pk = generate_keypair()
user_id = hexlify(user_pk.format(compressed=True)).decode("utf-8")


@pytest.fixture()
def get_all_db_manager():
    manager = AppointmentsDBM("get_all_tmp_db")
    # Add last know block for the Responder in the db

    yield manager

    manager.db.close()
    rmtree("get_all_tmp_db")


@pytest.fixture(scope="module", autouse=True)
def api(db_manager, carrier, block_processor, gatekeeper, run_bitcoind):
    sk, pk = generate_keypair()

    responder = Responder(db_manager, gatekeeper, carrier, block_processor)
    watcher = Watcher(
        db_manager,
        gatekeeper,
        block_processor,
        responder,
        sk.to_der(),
        MAX_APPOINTMENTS,
        config.get("BLOCK_CACHE_SIZE"),
    )
    inspector = Inspector(block_processor, config.get("MIN_TO_SELF_DELAY"))
    api = API(config.get("API_HOST"), config.get("API_PORT"), inspector, watcher)

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


def add_appointment(client, appointment_data, user_id):
    r = client.post(add_appointment_endpoint, json=appointment_data)

    if r.status_code == HTTP_OK:
        locator = appointment_data.get("appointment").get("locator")
        uuid = hash_160("{}{}".format(locator, user_id))
        appointments[uuid] = appointment_data["appointment"]

    return r


def test_register(client, api):
    current_height = api.watcher.block_processor.get_block_count()
    data = {"public_key": user_id}
    r = client.post(register_endpoint, json=data)
    assert r.status_code == HTTP_OK
    assert r.json.get("public_key") == user_id
    assert r.json.get("available_slots") == config.get("DEFAULT_SLOTS")
    assert r.json.get("subscription_expiry") == current_height + config.get("DEFAULT_SUBSCRIPTION_DURATION")


def test_register_top_up(client, api):
    # Calling register more than once will give us DEFAULT_SLOTS * number_of_calls slots.
    # It will also refresh the expiry.
    temp_sk, tmp_pk = generate_keypair()
    tmp_user_id = hexlify(tmp_pk.format(compressed=True)).decode("utf-8")
    current_height = api.watcher.block_processor.get_block_count()

    data = {"public_key": tmp_user_id}

    for i in range(10):
        r = client.post(register_endpoint, json=data)
        assert r.status_code == HTTP_OK
        assert r.json.get("public_key") == tmp_user_id
        assert r.json.get("available_slots") == config.get("DEFAULT_SLOTS") * (i + 1)
        assert r.json.get("subscription_expiry") == current_height + config.get("DEFAULT_SUBSCRIPTION_DURATION")


def test_register_no_client_pk(client):
    data = {}
    r = client.post(register_endpoint, json=data)
    assert r.status_code == HTTP_BAD_REQUEST


def test_register_wrong_client_pk(client):
    data = {"public_key": user_id + user_id}
    r = client.post(register_endpoint, json=data)
    assert r.status_code == HTTP_BAD_REQUEST


def test_register_no_json(client):
    r = client.post(register_endpoint, data="random_message")
    assert r.status_code == HTTP_BAD_REQUEST
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_register_json_no_inner_dict(client):
    r = client.post(register_endpoint, json="random_message")
    assert r.status_code == HTTP_BAD_REQUEST
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_add_appointment(api, client, appointment):
    # Simulate the user registration (end time does not matter here)
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=0)

    # Properly formatted appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_OK
    assert r.json.get("available_slots") == 0


def test_add_appointment_no_json(api, client, appointment):
    # Simulate the user registration (end time does not matter here)
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=0)

    # No JSON data
    r = client.post(add_appointment_endpoint, data="random_message")
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Request is not json encoded" in r.json.get("error")
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_add_appointment_json_no_inner_dict(api, client, appointment):
    # Simulate the user registration (end time does not matter here)
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=0)

    # JSON data with no inner dict (invalid data format)
    r = client.post(add_appointment_endpoint, json="random_message")
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Invalid request content" in r.json.get("error")
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_add_appointment_wrong(api, client, appointment):
    # Simulate the user registration (end time does not matter here)
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=0)

    # Incorrect appointment (properly formatted, wrong data)
    appointment.to_self_delay = 0
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_BAD_REQUEST
    assert errors.APPOINTMENT_FIELD_TOO_SMALL == r.json.get("error_code")


def test_add_appointment_not_registered(api, client, appointment):
    # Properly formatted appointment, user is not registered
    tmp_sk, tmp_pk = generate_keypair()
    tmp_compressed_pk = hexlify(tmp_pk.format(compressed=True)).decode("utf-8")

    appointment_signature = Cryptographer.sign(appointment.serialize(), tmp_sk)
    r = add_appointment(
        client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, tmp_compressed_pk
    )
    assert r.status_code == HTTP_BAD_REQUEST
    assert errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS == r.json.get("error_code")


def test_add_appointment_registered_no_free_slots(api, client, appointment):
    # Empty the user slots (end time does not matter here)
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=0, subscription_expiry=0)

    # Properly formatted appointment, user has no available slots
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_BAD_REQUEST
    assert errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS == r.json.get("error_code")


def test_add_appointment_registered_not_enough_free_slots(api, client, appointment):
    # Give some slots to the user (end time does not matter here)
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=0)

    # Properly formatted appointment, user has not enough slots
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    # Let's create a big blob
    appointment.encrypted_blob = TWO_SLOTS_BLOTS

    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_BAD_REQUEST
    assert errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS == r.json.get("error_code")


def test_add_appointment_multiple_times_same_user(api, client, appointment, n=MULTIPLE_APPOINTMENTS):
    # Multiple appointments with the same locator should be valid and count as updates
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    # Simulate registering enough slots (end time does not matter here)
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=n, subscription_expiry=0)
    for _ in range(n):
        r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
        assert r.status_code == HTTP_OK
        assert r.json.get("available_slots") == n - 1

    # Since all updates came from the same user, only the last one is stored
    assert len(api.watcher.locator_uuid_map[appointment.locator]) == 1


def test_add_appointment_multiple_times_different_users(api, client, appointment, n=MULTIPLE_APPOINTMENTS):
    # If the same appointment comes from different users, all are kept
    # Create user keys and appointment signatures
    user_keys = [generate_keypair() for _ in range(n)]
    signatures = [Cryptographer.sign(appointment.serialize(), key[0]) for key in user_keys]
    compressed_pks = [hexlify(pk.format(compressed=True)).decode("utf-8") for sk, pk in user_keys]

    # Add one slot per public key
    for pair in user_keys:
        tmp_compressed_pk = hexlify(pair[1].format(compressed=True)).decode("utf-8")
        api.watcher.gatekeeper.registered_users[tmp_compressed_pk] = UserInfo(available_slots=2, subscription_expiry=0)

    # Send the appointments
    for compressed_pk, signature in zip(compressed_pks, signatures):
        r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": signature}, compressed_pk)
        assert r.status_code == HTTP_OK
        assert r.json.get("available_slots") == 1

    # Check that all the appointments have been added and that there are no duplicates
    assert len(set(api.watcher.locator_uuid_map[appointment.locator])) == n


def test_add_appointment_update_same_size(api, client, appointment):
    # Update an appointment by one of the same size and check that no additional slots are filled
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=0)

    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0

    # The user has no additional slots, but it should be able to update
    # Let's just reverse the encrypted blob for example
    appointment.encrypted_blob = appointment.encrypted_blob[::-1]
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0


def test_add_appointment_update_bigger(api, client, appointment):
    # Update an appointment by one bigger, and check additional slots are filled
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=2, subscription_expiry=0)

    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 1

    # The user has one slot, so it should be able to update as long as it only takes 1 additional slot
    appointment.encrypted_blob = TWO_SLOTS_BLOTS
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0

    # Check that it'll fail if no enough slots are available
    # Double the size from before
    appointment.encrypted_blob = TWO_SLOTS_BLOTS + TWO_SLOTS_BLOTS
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_BAD_REQUEST


def test_add_appointment_update_smaller(api, client, appointment):
    # Update an appointment by one bigger, and check slots are freed
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=2, subscription_expiry=0)
    # This should take 2 slots
    appointment.encrypted_blob = TWO_SLOTS_BLOTS
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0

    # Let's update with one just small enough
    appointment.encrypted_blob = "A" * (ENCRYPTED_BLOB_MAX_SIZE_HEX - 2)
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 1


def test_add_appointment_in_cache(api, client):
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=0)
    appointment, dispute_tx = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    # Add the data to the cache
    dispute_txid = api.watcher.block_processor.decode_raw_transaction(dispute_tx).get("txid")
    api.watcher.locator_cache.cache[appointment.locator] = dispute_txid

    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0

    # Trying to add it again should fail, since it is already in the Responder
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_BAD_REQUEST and r.json.get("error_code") == errors.APPOINTMENT_ALREADY_TRIGGERED

    # The appointment would be rejected even if the data is not in the cache provided we've it has been triggered
    del api.watcher.locator_cache.cache[appointment.locator]
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_BAD_REQUEST and r.json.get("error_code") == errors.APPOINTMENT_ALREADY_TRIGGERED


def test_add_appointment_in_cache_cannot_decrypt(api, client):
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=0)
    appointment, dispute_tx = generate_dummy_appointment()
    appointment.encrypted_blob = appointment.encrypted_blob[::-1]
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    # Add the data to the cache
    dispute_txid = api.watcher.block_processor.decode_raw_transaction(dispute_tx).get("txid")
    api.watcher.locator_cache.cache[dispute_txid] = appointment.locator

    # The appointment should be accepted
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0


def test_add_appointment_in_cache_invalid_transaction(api, client):
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=0)

    # We need to create the appointment manually
    dispute_tx = create_dummy_transaction()
    dispute_txid = dispute_tx.tx_id.hex()
    penalty_tx = create_dummy_transaction(dispute_txid)

    locator = compute_locator(dispute_txid)
    dummy_appointment_data = {"tx": penalty_tx.hex(), "tx_id": dispute_txid, "to_self_delay": 20}
    encrypted_blob = Cryptographer.encrypt(dummy_appointment_data.get("tx")[::-1], dummy_appointment_data.get("tx_id"))

    appointment_data = {
        "locator": locator,
        "to_self_delay": dummy_appointment_data.get("to_self_delay"),
        "encrypted_blob": encrypted_blob,
        "user_id": get_random_value_hex(16),
    }

    appointment = ExtendedAppointment.from_dict(appointment_data)
    api.watcher.locator_cache.cache[appointment.locator] = dispute_tx.tx_id.hex()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    # Add the data to the cache
    api.watcher.locator_cache.cache[dispute_txid] = appointment.locator

    # The appointment should be accepted
    r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)
    assert r.status_code == HTTP_OK and r.json.get("available_slots") == 0


def test_add_too_many_appointment(api, client):
    # Give slots to the user
    api.watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=200, subscription_expiry=0)

    free_appointment_slots = MAX_APPOINTMENTS - len(api.watcher.appointments)

    for i in range(free_appointment_slots + 1):
        appointment, dispute_tx = generate_dummy_appointment()
        locator_dispute_tx_map[appointment.locator] = dispute_tx

        appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
        r = add_appointment(client, {"appointment": appointment.to_dict(), "signature": appointment_signature}, user_id)

        if i < free_appointment_slots:
            assert r.status_code == HTTP_OK
        else:
            assert r.status_code == HTTP_SERVICE_UNAVAILABLE


def test_get_appointment_no_json(api, client, appointment):
    r = client.post(add_appointment_endpoint, data="random_message")
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Request is not json encoded" in r.json.get("error")
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_get_appointment_json_no_inner_dict(api, client, appointment):
    r = client.post(add_appointment_endpoint, json="random_message")
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Invalid request content" in r.json.get("error")
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_get_random_appointment_registered_user(client, user_sk=user_sk):
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    message = "get appointment {}".format(locator)
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    data = {"locator": locator, "signature": signature}
    r = client.post(get_appointment_endpoint, json=data)

    # We should get a 404 not found since we are using a made up locator
    received_appointment = r.json
    assert r.status_code == HTTP_NOT_FOUND
    assert received_appointment.get("status") == "not_found"


def test_get_appointment_not_registered_user(client):
    # Not registered users have no associated appointments, so this should fail
    tmp_sk, tmp_pk = generate_keypair()

    # The tower is designed so a not found appointment and a request from a non-registered user return the same error to
    # prevent probing.
    test_get_random_appointment_registered_user(client, tmp_sk)


def test_get_appointment_in_watcher(api, client, appointment):
    # Mock the appointment in the Watcher
    uuid = hash_160("{}{}".format(appointment.locator, user_id))
    api.watcher.db_manager.store_watcher_appointment(uuid, appointment.to_dict())

    # Next we can request it
    message = "get appointment {}".format(appointment.locator)
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    data = {"locator": appointment.locator, "signature": signature}
    r = client.post(get_appointment_endpoint, json=data)
    assert r.status_code == HTTP_OK

    # Check that the appointment is on the Watcher
    assert r.json.get("status") == "being_watched"

    # Check the the sent appointment matches the received one
    appointment_dict = appointment.to_dict()
    appointment_dict.pop("user_id")
    assert r.json.get("locator") == appointment.locator
    assert appointment.to_dict() == r.json.get("appointment")


def test_get_appointment_in_responder(api, client, appointment):
    # Mock the appointment in the Responder
    tracker_data = {
        "locator": appointment.locator,
        "dispute_txid": get_random_value_hex(32),
        "penalty_txid": get_random_value_hex(32),
        "penalty_rawtx": get_random_value_hex(250),
        "user_id": get_random_value_hex(16),
    }
    tx_tracker = TransactionTracker.from_dict(tracker_data)

    uuid = hash_160("{}{}".format(appointment.locator, user_id))
    api.watcher.db_manager.create_triggered_appointment_flag(uuid)
    api.watcher.responder.db_manager.store_responder_tracker(uuid, tx_tracker.to_dict())

    # Request back the data
    message = "get appointment {}".format(appointment.locator)
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    data = {"locator": appointment.locator, "signature": signature}

    # Next we can request it
    r = client.post(get_appointment_endpoint, json=data)
    assert r.status_code == HTTP_OK

    # Check that the appointment is on the Responder
    assert r.json.get("status") == "dispute_responded"

    # Check the the sent appointment matches the received one
    assert tx_tracker.locator == r.json.get("locator")
    assert tx_tracker.dispute_txid == r.json.get("appointment").get("dispute_txid")
    assert tx_tracker.penalty_txid == r.json.get("appointment").get("penalty_txid")
    assert tx_tracker.penalty_rawtx == r.json.get("appointment").get("penalty_rawtx")


def test_get_all_appointments_watcher(api, client, get_all_db_manager):
    # Let's reset the dbs so we can test this clean
    api.watcher.db_manager = get_all_db_manager
    api.watcher.responder.db_manager = get_all_db_manager

    # Check that they are wiped clean
    r = client.get(get_all_appointment_endpoint)
    assert r.status_code == HTTP_OK
    assert len(r.json.get("watcher_appointments")) == 0 and len(r.json.get("responder_trackers")) == 0

    # Add some appointments to the Watcher db
    non_triggered_appointments = {}
    for _ in range(10):
        uuid = get_random_value_hex(16)
        appointment, _ = generate_dummy_appointment()
        appointment.locator = get_random_value_hex(16)
        non_triggered_appointments[uuid] = appointment.to_dict()
        api.watcher.db_manager.store_watcher_appointment(uuid, appointment.to_dict())

    triggered_appointments = {}
    for _ in range(10):
        uuid = get_random_value_hex(16)
        appointment, _ = generate_dummy_appointment()
        appointment.locator = get_random_value_hex(16)
        triggered_appointments[uuid] = appointment.to_dict()
        api.watcher.db_manager.store_watcher_appointment(uuid, appointment.to_dict())
        api.watcher.db_manager.create_triggered_appointment_flag(uuid)

    # We should only get the non-triggered appointments
    r = client.get(get_all_appointment_endpoint)
    assert r.status_code == HTTP_OK

    watcher_locators = [v["locator"] for k, v in r.json["watcher_appointments"].items()]
    local_locators = [appointment["locator"] for uuid, appointment in non_triggered_appointments.items()]

    assert set(watcher_locators) == set(local_locators)
    assert len(r.json["responder_trackers"]) == 0


def test_get_all_appointments_responder(api, client, get_all_db_manager):
    # Let's reset the dbs so we can test this clean
    api.watcher.db_manager = get_all_db_manager
    api.watcher.responder.db_manager = get_all_db_manager

    # Check that they are wiped clean
    r = client.get(get_all_appointment_endpoint)
    assert r.status_code == HTTP_OK
    assert len(r.json.get("watcher_appointments")) == 0 and len(r.json.get("responder_trackers")) == 0

    # Add some trackers to the Responder db
    tx_trackers = {}
    for _ in range(10):
        uuid = get_random_value_hex(16)
        tracker_data = {
            "locator": get_random_value_hex(16),
            "dispute_txid": get_random_value_hex(32),
            "penalty_txid": get_random_value_hex(32),
            "penalty_rawtx": get_random_value_hex(250),
            "user_id": get_random_value_hex(16),
        }
        tracker = TransactionTracker.from_dict(tracker_data)
        tx_trackers[uuid] = tracker.to_dict()
        api.watcher.responder.db_manager.store_responder_tracker(uuid, tracker.to_dict())
        api.watcher.db_manager.create_triggered_appointment_flag(uuid)

    # Get all appointments
    r = client.get(get_all_appointment_endpoint)

    # Make sure there is not pending locator in the watcher
    responder_trackers = [v["locator"] for k, v in r.json["responder_trackers"].items()]
    local_locators = [tracker["locator"] for uuid, tracker in tx_trackers.items()]

    assert set(responder_trackers) == set(local_locators)
    assert len(r.json["watcher_appointments"]) == 0
