from multiprocessing import Event
import grpc
import pytest
from uuid import uuid4

from google.protobuf import json_format
from google.protobuf.empty_pb2 import Empty

from common.cryptographer import Cryptographer, hash_160

from teos.watcher import Watcher
from teos.responder import Responder
from teos.gatekeeper import UserInfo
from teos.internal_api import InternalAPI
from teos.protobuf.tower_services_pb2_grpc import TowerServicesStub
from teos.protobuf.tower_services_pb2 import GetTowerInfoResponse
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
from test.teos.unit.conftest import generate_keypair, get_random_value_hex

internal_api_endpoint = "{}:{}".format(config.get("INTERNAL_API_HOST"), config.get("INTERNAL_API_PORT"))

MAX_APPOINTMENTS = 100
teos_sk, teos_pk = generate_keypair()

user_sk, user_pk = generate_keypair()
user_id = Cryptographer.get_compressed_pk(user_pk)


@pytest.fixture(scope="module")
def internal_api(db_manager, gatekeeper, carrier, block_processor):
    responder = Responder(db_manager, gatekeeper, carrier, block_processor)
    watcher = Watcher(
        db_manager, gatekeeper, block_processor, responder, teos_sk, MAX_APPOINTMENTS, config.get("LOCATOR_CACHE_SIZE")
    )
    watcher.last_known_block = block_processor.get_best_block_hash()
    i_api = InternalAPI(watcher, internal_api_endpoint, config.get("INTERNAL_API_WORKERS"), Event())
    i_api.rpc_server.start()

    yield i_api

    i_api.rpc_server.stop(None)


@pytest.fixture()
def clear_state(internal_api, db_manager):
    """If added to a test, it will clear the db and all the appointments in the watcher and responder before running
    the test"""
    internal_api.watcher.gatekeeper.registered_users = dict()
    internal_api.watcher.appointments = dict()
    internal_api.watcher.responder.trackers = dict()
    for key, _ in db_manager.db.iterator():
        db_manager.db.delete(key)


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


def test_register(internal_api, stub):
    # Normal request should work just fine
    response = stub.register(RegisterRequest(user_id=user_id))
    assert isinstance(response, RegisterResponse)


def test_register_wrong_user_id(internal_api, stub):
    # If the user id is wrong we should get INVALID_ARGUMENT with the proper message
    wrong_user_id = get_random_value_hex(32)

    with pytest.raises(grpc.RpcError) as e:
        stub.register(RegisterRequest(user_id=wrong_user_id))
    assert e.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert "Provided public key does not match expected format" in e.value.details()


# FIXME: 194 will do with dummy appointment
def test_add_appointment(internal_api, stub, generate_dummy_appointment):
    # Normal request should work just fine (user needs to be registered)
    stub.register(RegisterRequest(user_id=user_id))

    appointment, _ = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    response = send_appointment(stub, appointment, appointment_signature)

    assert isinstance(response, AddAppointmentResponse)


# FIXME: 194 will do with dummy appointment
def test_add_appointment_non_registered(internal_api, stub, generate_dummy_appointment):
    # If the user is not registered we should get UNAUTHENTICATED + the proper message
    another_user_sk, another_user_pk = generate_keypair()
    appointment, _ = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), another_user_sk)

    e = send_wrong_appointment(stub, appointment, appointment_signature)

    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert "Invalid signature or user does not have enough slots available" in e.value.details()


# FIXME: 194 will do with dummy appointment
def test_add_appointment_not_enough_slots(internal_api, stub, generate_dummy_appointment):
    # UNAUTHENTICATED should also be get if the user does not have enough appointment slots
    # Register the user and set the slots to 0
    stub.register(RegisterRequest(user_id=user_id))
    internal_api.watcher.gatekeeper.registered_users[user_id].available_slots = 0

    appointment, _ = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    e = send_wrong_appointment(stub, appointment, appointment_signature)

    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert "Invalid signature or user does not have enough slots available" in e.value.details()


# FIXME: 194 will do with dummy appointment
def test_add_appointment_subscription_expired(internal_api, stub, generate_dummy_appointment):
    # UNAUTHENTICATED is returned if the subscription has expired
    # Register the user and set the expiry to the current block
    stub.register(RegisterRequest(user_id=user_id))
    internal_api.watcher.gatekeeper.registered_users[
        user_id
    ].subscription_expiry = internal_api.watcher.block_processor.get_block_count()

    appointment, _ = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    e = send_wrong_appointment(stub, appointment, appointment_signature)

    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert "Your subscription expired at" in e.value.details()


# FIXME: 194 will do with dummy appointment
def test_add_appointment_limit_reached(internal_api, stub, generate_dummy_appointment, monkeypatch):
    # If the tower appointment limit is reached RESOURCE_EXHAUSTED should be returned
    monkeypatch.setattr(internal_api.watcher, "max_appointments", 0)

    stub.register(RegisterRequest(user_id=user_id))

    appointment, _ = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    e = send_wrong_appointment(stub, appointment, appointment_signature)

    assert e.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
    assert "Appointment limit reached" in e.value.details()


# FIXME: 194 will do with dummy appointment
def test_add_appointment_already_triggered(internal_api, stub, generate_dummy_appointment):
    # If the appointment has already been trigger we should get ALREADY_EXISTS
    stub.register(RegisterRequest(user_id=user_id))

    appointment, _ = generate_dummy_appointment()
    appointment_uuid = hash_160("{}{}".format(appointment.locator, user_id))
    # Adding the uuid to the Responder trackers so the Watcher thinks it is in there. The data does not actually matters
    internal_api.watcher.responder.trackers[appointment_uuid] = {}
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    e = send_wrong_appointment(stub, appointment, appointment_signature)

    assert e.value.code() == grpc.StatusCode.ALREADY_EXISTS
    assert "The provided appointment has already been triggered" in e.value.details()


# FIXME: 194 will do with dummy appointment
def test_get_appointment(internal_api, stub, generate_dummy_appointment):
    # Requests should work provided the user is registered and the appointment exists for him
    stub.register(RegisterRequest(user_id=user_id))

    # Send the appointment first
    appointment, _ = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    send_appointment(stub, appointment, appointment_signature)

    # Request it back
    message = f"get appointment {appointment.locator}"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    response = stub.get_appointment(GetAppointmentRequest(locator=appointment.locator, signature=request_signature))

    assert isinstance(response, GetAppointmentResponse)


# FIXME: 194 will do with dummy appointment
def test_get_appointment_non_registered(internal_api, stub, generate_dummy_appointment):
    # If the user is not registered or the appointment does not belong to him the response should be NOT_FOUND
    stub.register(RegisterRequest(user_id=user_id))
    another_user_sk, another_user_pk = generate_keypair()

    # Send the appointment first
    appointment, _ = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    send_appointment(stub, appointment, appointment_signature)

    # Request it back
    message = f"get appointment {appointment.locator}"
    request_signature = Cryptographer.sign(message.encode("utf-8"), another_user_sk)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_appointment(GetAppointmentRequest(locator=appointment.locator, signature=request_signature))

    assert e.value.code() == grpc.StatusCode.NOT_FOUND
    assert "Appointment not found" in e.value.details()

    # Notice how the request will succeed if `user` (user_id) requests it
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    response = stub.get_appointment(GetAppointmentRequest(locator=appointment.locator, signature=request_signature))
    assert isinstance(response, GetAppointmentResponse)


def test_get_appointment_non_existent(internal_api, stub):
    # Non-existing appointment will also return NOT_FOUND
    stub.register(RegisterRequest(user_id=user_id))

    # Request it back
    locator = get_random_value_hex(16)
    message = f"get appointment {locator}"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_appointment(GetAppointmentRequest(locator=locator, signature=request_signature))

    assert e.value.code() == grpc.StatusCode.NOT_FOUND
    assert "Appointment not found" in e.value.details()


# FIXME: 194 will do with dummy appointment
def test_get_appointment_subscription_expired(internal_api, stub, generate_dummy_appointment):
    # UNAUTHENTICATED is returned if the subscription has expired
    stub.register(RegisterRequest(user_id=user_id))

    # Send the appointment first
    appointment, _ = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    send_appointment(stub, appointment, appointment_signature)

    # Modify the user data so the subscription has already ended
    expiry = internal_api.watcher.block_processor.get_block_count() - internal_api.watcher.gatekeeper.expiry_delta - 1
    internal_api.watcher.gatekeeper.registered_users[user_id].subscription_expiry = expiry

    # Request it back
    message = f"get appointment {appointment.locator}"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_appointment(GetAppointmentRequest(locator=appointment.locator, signature=request_signature))

    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert "Your subscription expired at" in e.value.details()


def test_get_subscription_info(internal_api, stub):
    stub.register(RegisterRequest(user_id=user_id))

    # Request subscription details
    message = "get subscription info"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)
    response = stub.get_subscription_info(GetSubscriptionInfoRequest(signature=request_signature))

    assert isinstance(response, GetUserResponse)


def test_get_subscription_info_expired(internal_api, stub):
    stub.register(RegisterRequest(user_id=user_id))

    # Modify the user data so the subscription has already ended
    expiry = internal_api.watcher.block_processor.get_block_count() - internal_api.watcher.gatekeeper.expiry_delta - 1
    internal_api.watcher.gatekeeper.registered_users[user_id].subscription_expiry = expiry

    # Request subscription details
    message = "get subscription info"
    request_signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    with pytest.raises(grpc.RpcError) as e:
        stub.get_subscription_info(GetSubscriptionInfoRequest(signature=request_signature))

    assert e.value.code() == grpc.StatusCode.UNAUTHENTICATED
    assert "Your subscription expired at" in e.value.details()


# METHODS ACCESSIBLE BY THE CLI
# The following collection of tests are for methods the CLI can reach and, therefore, have a softer security model than
# the previous set. Notice the currently there is not even authentication for the CLI (FIXME)


def test_get_all_appointments(clear_state, internal_api, stub):
    response = stub.get_all_appointments(Empty())
    assert isinstance(response, GetAllAppointmentsResponse)
    appointments = dict(response.appointments)
    assert len(appointments.get("watcher_appointments")) == 0 and len(appointments.get("responder_trackers")) == 0


# FIXME: 194 will do with dummy appointment
def test_get_all_appointments_watcher(clear_state, internal_api, generate_dummy_appointment, stub):
    # Data is pulled straight from the database, so we need to feed some
    appointment, _ = generate_dummy_appointment()
    uuid = uuid4().hex
    internal_api.watcher.db_manager.store_watcher_appointment(uuid, appointment.to_dict())

    response = stub.get_all_appointments(Empty())
    appointments = dict(response.appointments)

    assert len(appointments.get("watcher_appointments")) == 1 and len(appointments.get("responder_trackers")) == 0
    assert dict(appointments.get("watcher_appointments")[uuid]) == appointment.to_dict()


# FIXME: 194 will do with dummy tracker
def test_get_all_appointments_responder(clear_state, internal_api, generate_dummy_tracker, stub):
    # Data is pulled straight from the database, so we need to feed some
    tracker = generate_dummy_tracker()
    uuid = uuid4().hex
    internal_api.watcher.db_manager.store_responder_tracker(uuid, tracker.to_dict())

    response = stub.get_all_appointments(Empty())
    appointments = dict(response.appointments)

    assert len(appointments.get("watcher_appointments")) == 0 and len(appointments.get("responder_trackers")) == 1
    assert dict(appointments.get("responder_trackers")[uuid]) == tracker.to_dict()


# FIXME: 194 will do with dummy appointments and trackers
def test_get_all_appointments_both(clear_state, internal_api, generate_dummy_appointment, generate_dummy_tracker, stub):
    # Data is pulled straight from the database, so we need to feed some
    appointment, _ = generate_dummy_appointment()
    uuid_appointment = uuid4().hex
    internal_api.watcher.db_manager.store_watcher_appointment(uuid_appointment, appointment.to_dict())

    tracker = generate_dummy_tracker()
    uuid_tracker = uuid4().hex
    internal_api.watcher.db_manager.store_responder_tracker(uuid_tracker, tracker.to_dict())

    response = stub.get_all_appointments(Empty())
    appointments = dict(response.appointments)

    assert len(appointments.get("watcher_appointments")) == 1 and len(appointments.get("responder_trackers")) == 1
    assert dict(appointments.get("watcher_appointments")[uuid_appointment]) == appointment.to_dict()
    assert dict(appointments.get("responder_trackers")[uuid_tracker]) == tracker.to_dict()


def test_get_tower_info_empty(clear_state, internal_api, stub):
    response = stub.get_tower_info(Empty())
    assert isinstance(response, GetTowerInfoResponse)
    assert response.tower_id == Cryptographer.get_compressed_pk(teos_pk)
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
    # it doesn't matter they are not valid user ids for the test
    mock_users = ["user1", "user2", "user3"]
    monkeypatch.setattr(
        internal_api.watcher.gatekeeper, "registered_users", {"user1": dict(), "user2": dict(), "user3": dict()}
    )

    response = stub.get_users(Empty())
    assert isinstance(response, GetUsersResponse)
    assert response.user_ids == mock_users


def test_get_user(internal_api, stub, monkeypatch):
    # it doesn't matter they are not valid user ids and user data object for this test
    mock_user_id = "02c73bad28b78dd7e3bcad609d330e0d60b97fa0e08ca1cf486cb6cab8dd6140ac"
    mock_available_slots = 100
    mock_subscription_expiry = 1234
    mock_user_info = UserInfo(mock_available_slots, mock_subscription_expiry)

    def mock_get_user_info(user_id):
        if user_id == mock_user_id:
            return mock_user_info
        else:
            raise RuntimeError(f"called with an unexpected user_id: {user_id}")

    monkeypatch.setattr(internal_api.watcher, "get_user_info", mock_get_user_info)

    response = stub.get_user(GetUserRequest(user_id=mock_user_id))
    assert isinstance(response, GetUserResponse)

    # FIXME: numbers are currently returned as floats, even if they are integers
    assert json_format.MessageToDict(response.user) == {
        "appointments": [],
        "available_slots": float(mock_available_slots),
        "subscription_expiry": float(mock_subscription_expiry),
    }


def test_get_user_not_found(internal_api, stub):
    mock_user_id = "some_non_existing_user_id"

    with pytest.raises(grpc.RpcError) as e:
        stub.get_user(GetUserRequest(user_id=mock_user_id))

    assert e.value.code() == grpc.StatusCode.NOT_FOUND
    assert "User not found" in e.value.details()


def test_stop(internal_api, stub):
    stub.stop(Empty())

    assert internal_api.stop_command_event.is_set()
