import grpc
import pytest
from uuid import uuid4
from multiprocessing import Event
from google.protobuf import json_format
from google.protobuf.empty_pb2 import Empty


from common.cryptographer import Cryptographer

from teos.watcher import Watcher
from teos.responder import Responder
from teos.gatekeeper import UserInfo
from teos.internal_api import (
    InternalAPI,
    SubscriptionExpired,
    AppointmentLimitReached,
    AppointmentAlreadyTriggered,
    AppointmentNotFound,
    AppointmentStatus,
)
from teos.protobuf.tower_services_pb2 import GetTowerInfoResponse
from teos.protobuf.tower_services_pb2_grpc import TowerServicesStub
from teos.protobuf.user_pb2 import (
    RegisterRequest,
    RegisterResponse,
    GetUsersResponse,
    GetUserRequest,
    GetUserResponse,
    GetSubscriptionInfoRequest,
)
from teos.protobuf.appointment_pb2 import (
    Appointment,
    AddAppointmentRequest,
    AddAppointmentResponse,
    GetAppointmentRequest,
    GetAppointmentResponse,
    GetAllAppointmentsResponse,
)

from test.teos.conftest import config
from test.teos.unit.mocks import AppointmentsDBM as DBManagerMock
from test.teos.unit.conftest import (
    generate_keypair,
    get_random_value_hex,
    mock_connection_refused_return,
    raise_invalid_parameter,
    raise_auth_failure,
    raise_not_enough_slots,
)


internal_api_endpoint = "{}:{}".format(config.get("INTERNAL_API_HOST"), config.get("INTERNAL_API_PORT"))

MAX_APPOINTMENTS = 100
teos_sk, teos_pk = generate_keypair()
teos_id = Cryptographer.get_compressed_pk(teos_pk)

user_sk, user_pk = generate_keypair()
user_id = Cryptographer.get_compressed_pk(user_pk)


def raise_subscription_expired(*args, **kwargs):
    # Message is passed in the API response
    raise SubscriptionExpired("Your subscription expired at")


def raise_appointment_limit_reached(*args, **kwargs):
    raise AppointmentLimitReached("")


def raise_appointment_already_triggered(*args, **kwargs):
    raise AppointmentAlreadyTriggered("")


def raise_appointment_not_found(*args, **kwargs):
    raise AppointmentNotFound("")


@pytest.fixture(scope="module")
def internal_api(gatekeeper_mock, carrier_mock):
    db_manager = DBManagerMock()
    responder = Responder(db_manager, gatekeeper_mock, carrier_mock, gatekeeper_mock.block_processor)
    watcher = Watcher(
        db_manager,
        gatekeeper_mock,
        gatekeeper_mock.block_processor,
        responder,
        teos_sk,
        MAX_APPOINTMENTS,
        config.get("LOCATOR_CACHE_SIZE"),
    )

    i_api = InternalAPI(watcher, internal_api_endpoint, config.get("INTERNAL_API_WORKERS"), Event())
    i_api.rpc_server.start()

    yield i_api

    i_api.rpc_server.stop(None)


@pytest.fixture()
def stub():
    return TowerServicesStub(grpc.insecure_channel(internal_api_endpoint))


def send_appointment(stub, appointment, signature):
    response = stub.add_appointment(
        AddAppointmentRequest(
            appointment=Appointment(
                locator=appointment.locator,
                encrypted_blob=appointment.encrypted_blob,
                to_self_delay=appointment.to_self_delay,
            ),
            signature=signature,
        )
    )

    return response


def send_wrong_appointment(stub, appointment, signature):
    with pytest.raises(grpc.RpcError) as e:
        send_appointment(stub, appointment, signature)
    return e


# METHODS ACCESSIBLE BY THE CLIENT
# The following collection of tests are of methods the client can reach and, therefore, need to be properly
# authenticated at the application level as well as check for input data correctness


def test_register(internal_api, stub, monkeypatch):
    # Normal request should work just fine

    # Monkeypatch the response from the Watcher
    slots = 100
    expiry = 1000
    sig = get_random_value_hex(73)
    monkeypatch.setattr(internal_api.watcher, "register", lambda x: (slots, expiry, sig))

    response = stub.register(RegisterRequest(user_id=user_id))
    assert isinstance(response, RegisterResponse)


def test_register_wrong_user_id(internal_api, stub, monkeypatch):
    # If the user id is wrong we should get INVALID_ARGUMENT with the proper message
    wrong_user_id = get_random_value_hex(32)

    # Monkeypatch the response from the Watcher
    monkeypatch.setattr(internal_api.watcher, "register", raise_invalid_parameter)

    with pytest.raises(grpc.RpcError) as e:
        stub.register(RegisterRequest(user_id=wrong_user_id))

        assert e.value.code() == grpc.StatusCode.INVALID_ARGUMENT
        assert "Provided public key does not match expected format" in e.value.details()


def test_add_appointment(internal_api, stub, generate_dummy_appointment, monkeypatch):
    # Normal request should work just fine
    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    # Mock the return from the Watcher
    data = {
        "locator": appointment.locator,
        "start_block": 100,
        "signature": get_random_value_hex(71),
        "available_slots": 100,
        "subscription_expiry": 1000,
    }
    monkeypatch.setattr(internal_api.watcher, "add_appointment", lambda x, y: data)
    response = send_appointment(stub, appointment, appointment_signature)

    assert isinstance(response, AddAppointmentResponse)


def test_add_appointment_non_registered(internal_api, stub, generate_dummy_appointment, monkeypatch):
    # If the user is not registered we should get UNAUTHENTICATED + the proper error message

    # Mock not registered user
    monkeypatch.setattr(internal_api.watcher, "add_appointment", raise_auth_failure)

    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    e = send_wrong_appointment(stub, appointment, appointment_signature)
    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert "Invalid signature or user does not have enough slots available" in e.value.details()


def test_add_appointment_not_enough_slots(internal_api, stub, generate_dummy_appointment, monkeypatch):
    # UNAUTHENTICATED should also be get if the user does not have enough appointment slots

    # Mock user with 0 slots
    monkeypatch.setattr(internal_api.watcher, "add_appointment", raise_not_enough_slots)

    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    e = send_wrong_appointment(stub, appointment, appointment_signature)

    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert "Invalid signature or user does not have enough slots available" in e.value.details()


def test_add_appointment_subscription_expired(internal_api, stub, generate_dummy_appointment, monkeypatch):
    # UNAUTHENTICATED is returned if the subscription has expired

    # Mock a user with an expired subscription
    monkeypatch.setattr(internal_api.watcher, "add_appointment", raise_subscription_expired)

    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    e = send_wrong_appointment(stub, appointment, appointment_signature)

    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert "Your subscription expired at" in e.value.details()


def test_add_appointment_limit_reached(internal_api, stub, generate_dummy_appointment, monkeypatch):
    # If the tower appointment limit is reached RESOURCE_EXHAUSTED should be returned

    # Mock the Watcher's return
    monkeypatch.setattr(internal_api.watcher, "add_appointment", raise_appointment_limit_reached)

    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    e = send_wrong_appointment(stub, appointment, appointment_signature)

    assert e.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
    assert "Appointment limit reached" in e.value.details()


def test_add_appointment_already_triggered(internal_api, stub, generate_dummy_appointment, monkeypatch):
    # If the appointment has already been trigger we should get ALREADY_EXISTS

    # Mock the Watcher's return
    monkeypatch.setattr(internal_api.watcher, "add_appointment", raise_appointment_already_triggered)

    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    e = send_wrong_appointment(stub, appointment, appointment_signature)

    assert e.value.code() == grpc.StatusCode.ALREADY_EXISTS
    assert "The provided appointment has already been triggered" in e.value.details()


def test_get_appointment(internal_api, stub, generate_dummy_appointment, monkeypatch):
    # Requests should work provided the user is registered and the appointment exists for him
    # Create an appointment and mock the return from the Watcher (the appointment status is not relevant here)
    appointment = generate_dummy_appointment()
    monkeypatch.setattr(
        internal_api.watcher, "get_appointment", lambda x, y: (appointment.to_dict(), AppointmentStatus.BEING_WATCHED)
    )

    # Request it back
    message = f"get appointment {appointment.locator}"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    response = stub.get_appointment(GetAppointmentRequest(locator=appointment.locator, signature=request_signature))

    assert isinstance(response, GetAppointmentResponse)


def test_get_appointment_non_registered(internal_api, stub, generate_dummy_appointment, monkeypatch):
    # If the user is not registered or the appointment does not belong to him the response should be NOT_FOUND

    # Mock the response from the Watcher
    monkeypatch.setattr(internal_api.watcher, "get_appointment", raise_auth_failure)

    # Send the request as an non-registered user
    locator = get_random_value_hex(32)
    message = f"get appointment {locator}"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_appointment(GetAppointmentRequest(locator=locator, signature=request_signature))

        assert e.value.code() == grpc.StatusCode.NOT_FOUND
        assert "Appointment not found" in e.value.details()


def test_get_appointment_non_existent(internal_api, stub, monkeypatch):
    # Non-existing appointment will also return NOT_FOUND

    # Mock the response from the Watcher
    monkeypatch.setattr(internal_api.watcher, "get_appointment", raise_appointment_not_found)

    # Request a non-existing appointment
    locator = get_random_value_hex(16)
    message = f"get appointment {locator}"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_appointment(GetAppointmentRequest(locator=locator, signature=request_signature))

        assert e.value.code() == grpc.StatusCode.NOT_FOUND
        assert "Appointment not found" in e.value.details()


def test_get_appointment_subscription_expired(internal_api, stub, generate_dummy_appointment, monkeypatch):
    # UNAUTHENTICATED is returned if the subscription has expired

    # Mock a user with an expired subscription
    monkeypatch.setattr(internal_api.watcher, "get_appointment", raise_subscription_expired)

    # Request the data
    locator = get_random_value_hex(32)
    message = f"get appointment {locator}"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_appointment(GetAppointmentRequest(locator=locator, signature=request_signature))

        assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
        assert "Your subscription expired at" in e.value.details()


def test_get_subscription_info(internal_api, stub, monkeypatch):
    # Requesting the subscription info for a registered user should work

    # Mock the user being there. Data is not relevant since we only care about the type of response.
    subscription_info = UserInfo(100, [], 1000)
    monkeypatch.setattr(internal_api.watcher, "get_subscription_info", lambda x: (subscription_info, []))

    # Request subscription details
    message = "get subscription info"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    response = stub.get_subscription_info(GetSubscriptionInfoRequest(signature=request_signature))

    assert isinstance(response, GetUserResponse)


def test_get_subscription_info_non_registered(internal_api, stub, monkeypatch):
    # Requesting the subscription info for a non-registered user should fail

    # Mock the user not being there.
    monkeypatch.setattr(internal_api.watcher, "get_subscription_info", raise_auth_failure)

    message = "get subscription info"
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_subscription_info(GetSubscriptionInfoRequest(signature=signature))

        assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
        assert "User not found. Have you registered?" in e.value.details()


def test_get_subscription_info_expired(internal_api, stub, monkeypatch):
    # Requesting the subscription info for expired users should fail

    # Mock the user not being there.
    monkeypatch.setattr(internal_api.watcher, "get_subscription_info", raise_subscription_expired)

    # Request subscription details
    message = "get subscription info"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_subscription_info(GetSubscriptionInfoRequest(signature=request_signature))

        assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
        assert "Your subscription expired at" in e.value.details()


# METHODS ACCESSIBLE BY THE CLI
# The following collection of tests are for methods the CLI can reach and, therefore, have a softer security model than
# the previous set. Notice the currently there is not authentication for the CLI (FIXME: #230)


def test_get_all_appointments(internal_api, stub, generate_dummy_appointment, generate_dummy_tracker, monkeypatch):
    # get_all_appointments should return a dict with the appointments in the Watcher and Responder

    # Mock the Watcher's response to get_all_watcher_appointments and get_all_responder_trackers
    local_appointments = {uuid4().hex: generate_dummy_appointment().to_dict() for _ in range(4)}
    local_trackers = {uuid4().hex: generate_dummy_tracker().to_dict() for _ in range(2)}
    monkeypatch.setattr(internal_api.watcher, "get_all_watcher_appointments", lambda: local_appointments)
    monkeypatch.setattr(internal_api.watcher, "get_all_responder_trackers", lambda: local_trackers)

    # Get the response and cast it to dict
    response = stub.get_all_appointments(Empty())
    assert isinstance(response, GetAllAppointmentsResponse)
    appointments = json_format.MessageToDict(response.appointments)

    for uuid, appointment in local_appointments.items():
        assert dict(appointments.get("watcher_appointments")[uuid]) == appointment
    for uuid, tracker in local_trackers.items():
        assert dict(appointments.get("responder_trackers")[uuid]) == tracker


def test_get_all_appointments_watcher(internal_api, stub, generate_dummy_appointment, monkeypatch):
    #  Mock data being only present in the Watcher
    local_appointments = {uuid4().hex: generate_dummy_appointment().to_dict()}
    monkeypatch.setattr(internal_api.watcher, "get_all_watcher_appointments", lambda: local_appointments)
    monkeypatch.setattr(internal_api.watcher, "get_all_responder_trackers", lambda: {})

    # Get the response and cast it to dict
    response = stub.get_all_appointments(Empty())
    assert isinstance(response, GetAllAppointmentsResponse)
    appointments = json_format.MessageToDict(response.appointments)

    assert len(appointments.get("responder_trackers")) == 0
    for uuid, appointment in local_appointments.items():
        assert appointments.get("watcher_appointments")[uuid] == appointment


def test_get_all_appointments_responder(internal_api, stub, generate_dummy_tracker, monkeypatch):
    #  Mock data being only present in the Watcher
    local_trackers = {uuid4().hex: generate_dummy_tracker().to_dict()}
    monkeypatch.setattr(internal_api.watcher, "get_all_watcher_appointments", lambda: {})
    monkeypatch.setattr(internal_api.watcher, "get_all_responder_trackers", lambda: local_trackers)

    # Get the response and cast it to dict
    response = stub.get_all_appointments(Empty())
    assert isinstance(response, GetAllAppointmentsResponse)
    appointments = json_format.MessageToDict(response.appointments)

    assert len(appointments.get("watcher_appointments")) == 0
    for uuid, tracker in local_trackers.items():
        assert dict(appointments.get("responder_trackers")[uuid]) == tracker


def test_get_tower_info_empty(internal_api, stub):
    response = stub.get_tower_info(Empty())
    assert isinstance(response, GetTowerInfoResponse)
    assert response.tower_id == teos_id
    assert response.n_registered_users == 0
    assert response.n_watcher_appointments == 0
    assert response.n_responder_trackers == 0


def test_get_tower_info(internal_api, stub, monkeypatch):
    monkeypatch.setattr(internal_api.watcher.gatekeeper, "registered_users", {"uid1": {}})
    monkeypatch.setattr(
        internal_api.watcher,
        "appointments",
        {
            "uid1": {"locator": "locator1", "user_id": "user_id1"},
            "uid2": {"locator": "locator2", "user_id": "user_id2"},
        },
    )
    monkeypatch.setattr(
        internal_api.watcher.responder,
        "trackers",
        {
            "uid1": {"penalty_txid": "txid1", "locator": "locator1", "user_id": "user_id1"},
            "uid2": {"penalty_txid": "txid2", "locator": "locator2", "user_id": "user_id2"},
            "uid3": {"penalty_txid": "txid3", "locator": "locator2", "user_id": "user_id3"},
        },
    )

    response = stub.get_tower_info(Empty())
    assert isinstance(response, GetTowerInfoResponse)
    assert response.tower_id == Cryptographer.get_compressed_pk(internal_api.watcher.signing_key.public_key)
    assert response.n_registered_users == 1
    assert response.n_watcher_appointments == 2
    assert response.n_responder_trackers == 3


def test_get_users(internal_api, stub, monkeypatch):
    # Mock user data (doesn't matter it's not properly formatted for the sake of the test)
    mock_users = ["user1", "user2", "user3"]
    monkeypatch.setattr(
        internal_api.watcher, "get_registered_user_ids", lambda: {"user1": dict(), "user2": dict(), "user3": dict()},
    )

    # Check we receive the same list of users
    response = stub.get_users(Empty())
    assert isinstance(response, GetUsersResponse)
    assert response.user_ids == mock_users


def test_get_user(internal_api, stub, monkeypatch):
    # Mock the Watcher's call return
    mock_user_id = "02c73bad28b78dd7e3bcad609d330e0d60b97fa0e08ca1cf486cb6cab8dd6140ac"
    mock_available_slots = 100
    mock_subscription_expiry = 1234
    mock_user_info = UserInfo(mock_available_slots, mock_subscription_expiry)

    monkeypatch.setattr(internal_api.watcher, "get_user_info", lambda x: mock_user_info)

    response = stub.get_user(GetUserRequest(user_id=mock_user_id))
    assert isinstance(response, GetUserResponse)

    # Numbers are currently returned as floats, even if they are integers. This is  due to gRPC.
    assert json_format.MessageToDict(response.user) == {
        "appointments": [],
        "available_slots": float(mock_available_slots),
        "subscription_expiry": float(mock_subscription_expiry),
    }


def test_get_user_not_found(internal_api, stub, monkeypatch):
    # Mock a non-registered user response
    monkeypatch.setattr(internal_api.watcher, "get_user_info", lambda x: None)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_user(GetUserRequest(user_id=get_random_value_hex(32)))

        assert e.value.code() == grpc.StatusCode.NOT_FOUND
        assert "User not found" in e.value.details()


def test_stop(internal_api, stub):
    # Test how the event changes when stop is called
    assert not internal_api.stop_command_event.is_set()
    stub.stop(Empty())
    assert internal_api.stop_command_event.is_set()


# TESTS WITH BITCOIND UNREACHABLE


def test_register_bitcoind_crash(internal_api, stub, monkeypatch):
    monkeypatch.setattr(internal_api.watcher, "register", mock_connection_refused_return)

    with pytest.raises(grpc.RpcError) as e:
        stub.register(RegisterRequest(user_id=user_id))

        assert e.value.code() == grpc.StatusCode.UNAVAILABLE
        assert "Service unavailable" in e.value.details()


def test_add_appointment_bitcoind_crash(internal_api, stub, generate_dummy_appointment, monkeypatch):
    monkeypatch.setattr(internal_api.watcher, "add_appointment", mock_connection_refused_return)

    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    with pytest.raises(grpc.RpcError) as e:
        send_appointment(stub, appointment, appointment_signature)

        assert e.value.code() == grpc.StatusCode.UNAVAILABLE
        assert "Service unavailable" in e.value.details()


def test_get_appointment_bitcoind_crash(internal_api, stub, monkeypatch):
    monkeypatch.setattr(internal_api.watcher, "get_appointment", mock_connection_refused_return)

    locator = get_random_value_hex(32)
    message = f"get appointment {locator}"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_appointment(GetAppointmentRequest(locator=locator, signature=request_signature))

        assert e.value.code() == grpc.StatusCode.UNAVAILABLE
        assert "Service unavailable" in e.value.details()


def test_get_subscription_info_bitcoind_crash(internal_api, stub, monkeypatch):
    monkeypatch.setattr(internal_api.watcher, "get_subscription_info", mock_connection_refused_return)

    message = "get subscription info"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    with pytest.raises(grpc.RpcError) as e:
        stub.get_subscription_info(GetSubscriptionInfoRequest(signature=request_signature))

        assert e.value.code() == grpc.StatusCode.UNAVAILABLE
        assert "Service unavailable" in e.value.details()
