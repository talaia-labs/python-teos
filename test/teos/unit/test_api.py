import grpc
import pytest

from teos.api import API
from teos.inspector import Inspector, InspectionFailed
from teos.internal_api import (
    RegisterResponse,
    AddAppointmentResponse,
    GetAppointmentResponse,
    AppointmentData,
    AppointmentProto,
    TrackerProto,
    Struct,
    GetUserResponse,
)


import common.errors as errors
import common.receipts as receipts
from common.cryptographer import Cryptographer
from common.appointment import Appointment, AppointmentStatus
from common.constants import (
    HTTP_OK,
    HTTP_EMPTY,
    HTTP_NOT_FOUND,
    HTTP_BAD_REQUEST,
    HTTP_SERVICE_UNAVAILABLE,
    LOCATOR_LEN_BYTES,
)

from test.teos.conftest import config
from test.teos.unit.conftest import (
    get_random_value_hex,
    generate_keypair,
    raise_invalid_parameter,
)

internal_api_endpoint = "{}:{}".format(config.get("INTERNAL_API_HOST"), config.get("INTERNAL_API_PORT"))

TEOS_API = "http://{}:{}".format(config.get("API_BIND"), config.get("API_PORT"))
ping_endpoint = "{}/ping".format(TEOS_API)
register_endpoint = "{}/register".format(TEOS_API)
add_appointment_endpoint = "{}/add_appointment".format(TEOS_API)
get_appointment_endpoint = "{}/get_appointment".format(TEOS_API)
get_all_appointment_endpoint = "{}/get_all_appointments".format(TEOS_API)
get_subscription_info_endpoint = "{}/get_subscription_info".format(TEOS_API)

# Reduce the maximum number of appointments to something we can test faster
MULTIPLE_APPOINTMENTS = 10


user_sk, user_pk = generate_keypair()
user_id = Cryptographer.get_compressed_pk(user_pk)

teos_sk, teos_pk = generate_keypair()
teos_id = Cryptographer.get_compressed_pk(teos_sk.public_key)

# Error code for gRPC error returns
rpc_error = grpc.RpcError()
rpc_error.code = None
rpc_error.details = None


# A function that ignores the arguments and returns user_id; used in some tests to mock the result of authenticate_user
def mock_authenticate_user(*args, **kwargs):
    return user_id


def raise_grpc_error(*args, **kwargs):
    raise rpc_error


def raise_inspection_failed(*args, **kwargs):
    raise InspectionFailed(args[0], args[1])


@pytest.fixture(scope="module", autouse=True)
def api():
    inspector = Inspector(config.get("MIN_TO_SELF_DELAY"))
    api = API(inspector, internal_api_endpoint)

    return api


@pytest.fixture()
def app(api):
    with api.app.app_context():
        yield api.app


@pytest.fixture
def client(app):
    return app.test_client()


def test_ping(client):
    r = client.get(ping_endpoint)
    assert r.status_code == HTTP_EMPTY


def test_register(api, client, monkeypatch):
    # Tests registering a user within the tower

    # Monkeypatch the response from the InternalAPI so the user is accepted
    slots = config.get("SUBSCRIPTION_SLOTS")
    expiry = config.get("SUBSCRIPTION_DURATION")
    receipt = receipts.create_registration_receipt(user_id, slots, expiry)
    signature = Cryptographer.sign(receipt, teos_sk)
    response = RegisterResponse(
        user_id=user_id, available_slots=slots, subscription_expiry=expiry, subscription_signature=signature,
    )
    monkeypatch.setattr(api.stub, "register", lambda x: response)

    #  Send the register request
    data = {"public_key": user_id}
    r = client.post(register_endpoint, json=data)

    # Check the reply
    assert r.status_code == HTTP_OK
    assert r.json.get("public_key") == user_id
    assert r.json.get("available_slots") == config.get("SUBSCRIPTION_SLOTS")
    assert r.json.get("subscription_expiry") == config.get("SUBSCRIPTION_DURATION")
    rpk = Cryptographer.recover_pk(receipt, r.json.get("subscription_signature"))
    assert Cryptographer.get_compressed_pk(rpk) == teos_id


def test_register_no_client_pk(client):
    # Register requests must contain the user public key, otherwise they will fail

    r = client.post(register_endpoint, json={})
    assert r.status_code == HTTP_BAD_REQUEST
    assert r.json.get("error") == "public_key not found in register message"
    assert r.json.get("error_code") == errors.REGISTRATION_MISSING_FIELD


def test_register_wrong_client_pk(api, client, monkeypatch):
    # Register requests with a wrongly formatter public key will also fail

    # MonkeyPatch the InternalAPI response
    e_code = grpc.StatusCode.INVALID_ARGUMENT
    monkeypatch.setattr(api.stub, "register", raise_grpc_error)
    monkeypatch.setattr(rpc_error, "code", lambda: e_code)
    monkeypatch.setattr(rpc_error, "details", lambda: "")

    data = {"public_key": user_id + user_id}
    r = client.post(register_endpoint, json=data)
    assert r.status_code == HTTP_BAD_REQUEST
    assert r.json.get("error_code") == errors.REGISTRATION_WRONG_FIELD_FORMAT


def test_register_no_json(api, client, monkeypatch):
    # Register requests with non-json bodies should fail
    r = client.post(register_endpoint, data="random_message")

    # MonkeyPatch the InternalAPI response
    monkeypatch.setattr(api.stub, "register", raise_invalid_parameter)

    assert r.status_code == HTTP_BAD_REQUEST
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_register_json_no_inner_dict(api, client, monkeypatch):
    # Register requests with wrongly formatted json bodies should fail
    r = client.post(register_endpoint, json="random_message")

    # MonkeyPatch the InternalAPI response
    monkeypatch.setattr(api.stub, "register", raise_invalid_parameter)

    assert r.status_code == HTTP_BAD_REQUEST
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_add_appointment(api, client, generate_dummy_appointment, monkeypatch):
    # Test adding a properly formatted appointment

    # Monkeypatch the InternalAPI return
    slots = 10
    subscription_expiry = 100
    appointment = generate_dummy_appointment()
    response = {
        "locator": appointment.locator,
        "start_block": appointment.start_block,
        "signature": get_random_value_hex(70),
        "available_slots": slots,
        "subscription_expiry": subscription_expiry,
    }
    monkeypatch.setattr(api.stub, "add_appointment", lambda x: AddAppointmentResponse(**response))

    # Properly formatted appointment
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = client.post(
        add_appointment_endpoint, json={"appointment": appointment.to_dict(), "signature": appointment_signature}
    )

    assert r.status_code == HTTP_OK
    assert r.json == response


def test_add_appointment_no_json(client):
    # An add_appointment request with a non-json body should fail
    r = client.post(add_appointment_endpoint, data="random_message")
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Request is not json encoded" in r.json.get("error")
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_add_appointment_json_no_inner_dict(client):
    # An add_appointment request with a wrongly formatted json body should also fail (no inner dict)
    r = client.post(add_appointment_endpoint, json="random_message")
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Invalid request content" in r.json.get("error")
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_add_appointment_wrong(api, client, generate_dummy_appointment, monkeypatch):
    # An add_appointment requests with properly formatted appointment but wrong data should fail

    # Mock an inspection failure in add_appointment
    errno = errors.APPOINTMENT_FIELD_TOO_SMALL
    errmsg = "inspection error msg"
    monkeypatch.setattr(
        api.inspector, "inspect", lambda x: raise_inspection_failed(errno, errmsg),
    )

    # Send the request
    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = client.post(
        add_appointment_endpoint, json={"appointment": appointment.to_dict(), "signature": appointment_signature}
    )
    assert r.status_code == HTTP_BAD_REQUEST
    assert r.json.get("error_code") == errno and errmsg in r.json.get("error")


def test_add_appointment_not_registered_no_enough_slots(api, client, generate_dummy_appointment, monkeypatch):
    # A properly formatted add appointment request:
    #   - from a non-registered user
    #   - from a user with no free slots
    #   - from a user with no enough free slots
    # should fail. To prevent probing, they all fail as UNAUTHENTICATED. Further testing can be done in the Watcher
    # but it's transparent from the API POV.

    # Mock the non-registered user (gRPC UNAUTHENTICATED error)
    e_code = grpc.StatusCode.UNAUTHENTICATED
    monkeypatch.setattr(api.stub, "add_appointment", raise_grpc_error)
    monkeypatch.setattr(rpc_error, "code", lambda: e_code)
    monkeypatch.setattr(rpc_error, "details", lambda: "")

    # Send the data
    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = client.post(
        add_appointment_endpoint, json={"appointment": appointment.to_dict(), "signature": appointment_signature}
    )
    assert r.status_code == HTTP_BAD_REQUEST
    assert errors.APPOINTMENT_INVALID_SIGNATURE_OR_SUBSCRIPTION_ERROR == r.json.get("error_code")


def test_add_appointment_multiple_times_same_user(api, client, generate_dummy_appointment, monkeypatch):
    # Multiple appointments with the same locator should be valid. At the API level we only need to test that
    # the request goes trough.
    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    # Monkeypatch the InternalAPI return
    slots = 10
    subscription_expiry = 100
    appointment = generate_dummy_appointment()
    response = {
        "locator": appointment.locator,
        "start_block": appointment.start_block,
        "signature": get_random_value_hex(70),
        "available_slots": slots,
        "subscription_expiry": subscription_expiry,
    }
    monkeypatch.setattr(api.stub, "add_appointment", lambda x: AddAppointmentResponse(**response))

    for _ in range(MULTIPLE_APPOINTMENTS):
        r = client.post(
            add_appointment_endpoint, json={"appointment": appointment.to_dict(), "signature": appointment_signature}
        )
        assert r.status_code == HTTP_OK
        assert r.json.get("available_slots") == slots
        assert r.json.get("start_block") == appointment.start_block


# DISCUSS: Any other add_appointment test were the appointment is accepted should be tested in the Watcher, given the
#          API is simply a passthrough for valid appointments, so they cannot be meaningfully tested from here.


def test_add_too_many_appointment(api, client, generate_dummy_appointment, monkeypatch):
    # If the appointment limit is reached, any other add_appointment request will fail
    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    # Mock the tower being out of slots (gRPC RESOURCE EXHAUSTED error)
    e_code = grpc.StatusCode.RESOURCE_EXHAUSTED
    monkeypatch.setattr(api.stub, "add_appointment", raise_grpc_error)
    monkeypatch.setattr(rpc_error, "code", lambda: e_code)
    monkeypatch.setattr(rpc_error, "details", lambda: "")

    r = client.post(
        add_appointment_endpoint, json={"appointment": appointment.to_dict(), "signature": appointment_signature}
    )
    assert r.status_code == HTTP_SERVICE_UNAVAILABLE


def test_get_appointment_no_json(client):
    # get_appointment requests with no json data must fail
    r = client.post(add_appointment_endpoint, data="random_message")
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Request is not json encoded" in r.json.get("error")
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_get_appointment_json_no_inner_dict(client):
    # get_appointment requests with json data but no inner dict must fail
    r = client.post(add_appointment_endpoint, json="random_message")
    assert r.status_code == HTTP_BAD_REQUEST
    assert "Invalid request content" in r.json.get("error")
    assert errors.INVALID_REQUEST_FORMAT == r.json.get("error_code")


def test_get_random_appointment_registered_user_or_non_registered(api, client, monkeypatch):
    # The tower is designed so a not found appointment and a request from a non-registered user return the same error to
    # prevent probing.
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    message = "get appointment {}".format(locator)
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    # Mock the user not having the appointment (gRPC NOT FOUND error)
    e_code = grpc.StatusCode.NOT_FOUND
    monkeypatch.setattr(api.stub, "get_appointment", raise_grpc_error)
    monkeypatch.setattr(rpc_error, "code", lambda: e_code)
    monkeypatch.setattr(rpc_error, "details", lambda: "")

    data = {"locator": locator, "signature": signature}
    r = client.post(get_appointment_endpoint, json=data)

    # We should get a 404 not found since we are using a made up locator
    assert r.status_code == HTTP_NOT_FOUND
    assert r.json.get("status") == AppointmentStatus.NOT_FOUND


def test_get_appointment_watcher(api, client, generate_dummy_appointment, monkeypatch):
    # Mock the appointment in the Watcher
    appointment = generate_dummy_appointment()
    app_data = AppointmentData(
        appointment=AppointmentProto(
            locator=appointment.locator,
            encrypted_blob=appointment.encrypted_blob,
            to_self_delay=appointment.to_self_delay,
        )
    )
    status = AppointmentStatus.BEING_WATCHED
    monkeypatch.setattr(
        api.stub, "get_appointment", lambda x: GetAppointmentResponse(appointment_data=app_data, status=status)
    )

    # Request it
    message = "get appointment {}".format(appointment.locator)
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    data = {"locator": appointment.locator, "signature": signature}
    r = client.post(get_appointment_endpoint, json=data)
    assert r.status_code == HTTP_OK

    # Check that requested appointment data matches the mocked one
    # Cast the extended appointment (used by the tower) to a regular appointment (used by the user)
    local_appointment = Appointment.from_dict(appointment.to_dict())
    assert r.json.get("status") == AppointmentStatus.BEING_WATCHED
    assert r.json.get("appointment") == local_appointment.to_dict()


def test_get_appointment_in_responder(api, client, generate_dummy_tracker, monkeypatch):
    # Mock the appointment in the Responder
    tracker = generate_dummy_tracker()
    track_data = AppointmentData(
        tracker=TrackerProto(
            locator=tracker.locator,
            dispute_txid=tracker.dispute_txid,
            penalty_txid=tracker.penalty_txid,
            penalty_rawtx=tracker.penalty_rawtx,
        )
    )
    status = AppointmentStatus.DISPUTE_RESPONDED
    monkeypatch.setattr(
        api.stub, "get_appointment", lambda x: GetAppointmentResponse(appointment_data=track_data, status=status)
    )

    # Request it
    message = "get appointment {}".format(tracker.locator)
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    data = {"locator": tracker.locator, "signature": signature}
    r = client.post(get_appointment_endpoint, json=data)
    assert r.status_code == HTTP_OK

    # Check the received tracker data matches the mocked one
    assert tracker.locator == r.json.get("locator")
    assert tracker.dispute_txid == r.json.get("appointment").get("dispute_txid")
    assert tracker.penalty_txid == r.json.get("appointment").get("penalty_txid")
    assert tracker.penalty_rawtx == r.json.get("appointment").get("penalty_rawtx")


def test_get_subscription_info(api, client, monkeypatch):
    # MonkeyPatch the InternalAPI response (user being in the tower)
    available_slots = 42
    subscription_expiry = 1234
    appointments = [get_random_value_hex(32)]

    user_struct = Struct()
    user_struct.update(
        {"subscription_expiry": subscription_expiry, "available_slots": available_slots, "appointments": appointments}
    )
    monkeypatch.setattr(api.stub, "get_subscription_info", lambda x: GetUserResponse(user=user_struct))

    # Request the data
    message = "get subscription info"
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    data = {"signature": signature}
    r = client.post(get_subscription_info_endpoint, json=data)

    # Check the data matches
    assert r.status_code == HTTP_OK
    assert r.get_json().get("available_slots") == available_slots
    assert r.get_json().get("subscription_expiry") == subscription_expiry
    assert r.get_json().get("appointments") == appointments


def test_get_subscription_info_unregistered_or_subscription_error(api, client, monkeypatch):
    # Mock the user not being registered (gRPC UNAUTHENTICATED error)
    e_code = grpc.StatusCode.UNAUTHENTICATED
    monkeypatch.setattr(api.stub, "get_subscription_info", raise_grpc_error)
    monkeypatch.setattr(rpc_error, "code", lambda: e_code)
    monkeypatch.setattr(rpc_error, "details", lambda: "")

    # Request the data
    message = "get subscription info"
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    data = {"signature": signature}
    r = client.post(get_subscription_info_endpoint, json=data)

    assert r.status_code == HTTP_BAD_REQUEST


# TESTS WITH BITCOIND UNREACHABLE
# All cases must return a gRPC UNAVAILABLE error


def test_register_bitcoind_crash(api, client, monkeypatch):
    # Monkeypatch register so it raises a ConnectionRejectedError (gRPC UNAVAILABLE)
    e_code = grpc.StatusCode.UNAVAILABLE
    monkeypatch.setattr(api.stub, "register", raise_grpc_error)
    monkeypatch.setattr(rpc_error, "code", lambda: e_code)
    monkeypatch.setattr(rpc_error, "details", lambda: "")

    data = {"public_key": user_id}
    r = client.post(register_endpoint, json=data)
    assert r.status_code == HTTP_SERVICE_UNAVAILABLE


def test_add_appointment_bitcoind_crash(api, client, generate_dummy_appointment, monkeypatch):
    # Monkeypatch add_appointment so it raises a ConnectionRejectedError (gRPC UNAVAILABLE)
    e_code = grpc.StatusCode.UNAVAILABLE
    monkeypatch.setattr(api.stub, "add_appointment", raise_grpc_error)
    monkeypatch.setattr(rpc_error, "code", lambda: e_code)
    monkeypatch.setattr(rpc_error, "details", lambda: "")

    appointment = generate_dummy_appointment()

    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    r = client.post(
        add_appointment_endpoint, json={"appointment": appointment.to_dict(), "signature": appointment_signature}
    )
    assert r.status_code == HTTP_SERVICE_UNAVAILABLE


def test_get_appointment_bitcoind_crash(api, client, monkeypatch):
    # Monkeypatch add_appointment so it raises a ConnectionRejectedError (gRPC UNAVAILABLE)
    e_code = grpc.StatusCode.UNAVAILABLE
    monkeypatch.setattr(api.stub, "get_appointment", raise_grpc_error)
    monkeypatch.setattr(rpc_error, "code", lambda: e_code)
    monkeypatch.setattr(rpc_error, "details", lambda: "")

    # Next we can request it
    locator = get_random_value_hex(16)
    message = "get appointment {}".format(locator)
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    data = {"locator": locator, "signature": signature}
    r = client.post(get_appointment_endpoint, json=data)
    assert r.status_code == HTTP_SERVICE_UNAVAILABLE


def test_get_subscription_info_bitcoind_crash(api, client, monkeypatch):
    # Monkeypatch get_subscription_info so it raises a ConnectionRejectedError (gRPC UNAVAILABLE)
    e_code = grpc.StatusCode.UNAVAILABLE
    monkeypatch.setattr(api.stub, "get_subscription_info", raise_grpc_error)
    monkeypatch.setattr(rpc_error, "code", lambda: e_code)
    monkeypatch.setattr(rpc_error, "details", lambda: "")

    # Request back the data
    message = "get subscription info"
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    data = {"signature": signature}

    # Next we can request the subscription info
    r = client.post(get_subscription_info_endpoint, json=data)
    assert r.status_code == HTTP_SERVICE_UNAVAILABLE
