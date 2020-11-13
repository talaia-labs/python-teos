import os
import json
from collections import namedtuple
import shutil
import pytest
import responses
from coincurve import PrivateKey
from requests.exceptions import ConnectionError

import common.receipts as receipts
from common.tools import compute_locator, is_compressed_pk
from common.appointment import Appointment, AppointmentStatus
from common.cryptographer import Cryptographer
from common.exceptions import InvalidParameter, InvalidKey, TowerResponseError

import contrib.client.teos_client as teos_client

from contrib.client.test.conftest import get_random_value_hex, get_config

config = get_config()

# dummy keys for the tests
dummy_user_sk = PrivateKey.from_int(1)
dummy_user_id = Cryptographer.get_compressed_pk(dummy_user_sk.public_key)
dummy_teos_sk = PrivateKey.from_int(2)
dummy_teos_id = Cryptographer.get_compressed_pk(dummy_teos_sk.public_key)
another_sk = PrivateKey.from_int(3)

teos_url = "http://{}:{}".format(config.get("API_CONNECT"), config.get("API_PORT"))
add_appointment_endpoint = "{}/add_appointment".format(teos_url)
register_endpoint = "{}/register".format(teos_url)
get_appointment_endpoint = "{}/get_appointment".format(teos_url)
get_all_appointments_endpoint = "{}/get_all_appointments".format(teos_url)
get_subscription_info_endpoint = "{}/get_subscription_info".format(teos_url)

dummy_appointment_data = {"tx": get_random_value_hex(192), "tx_id": get_random_value_hex(32), "to_self_delay": 200}

# This is the format appointment turns into once it hits "add_appointment"
dummy_appointment_dict = {
    "locator": compute_locator(dummy_appointment_data.get("tx_id")),
    "to_self_delay": dummy_appointment_data.get("to_self_delay"),
    "encrypted_blob": Cryptographer.encrypt(dummy_appointment_data.get("tx"), dummy_appointment_data.get("tx_id")),
}
dummy_appointment = Appointment.from_dict(dummy_appointment_dict)

dummy_user_data = {"appointments": [], "available_slots": 100, "subscription_expiry": 7000}

# The height is never checked in the tests, so we can make it up
CURRENT_HEIGHT = 300


@pytest.fixture
def keyfiles():
    # generate a private/public key pair, and an empty file, and return their names

    KeyFiles = namedtuple("KeyFiles", ["private_key_file_path", "public_key_file_path", "empty_file_path"])

    # Let's first create a private key and public key files
    private_key_file_path = "sk_test_file"
    public_key_file_path = "pk_test_file"
    empty_file_path = "empty_file"
    with open(private_key_file_path, "wb") as f:
        f.write(dummy_user_sk.to_der())
    with open(public_key_file_path, "wb") as f:
        f.write(dummy_user_sk.public_key.format(compressed=True))
    with open(empty_file_path, "wb"):
        pass

    yield KeyFiles(private_key_file_path, public_key_file_path, empty_file_path)

    # Remove the tmp files
    os.remove(private_key_file_path)
    os.remove(public_key_file_path)
    os.remove(empty_file_path)


@pytest.fixture
def post_response():
    # Create a response for the post requests to the tower
    return {
        "locator": dummy_appointment.to_dict()["locator"],
        "signature": Cryptographer.sign(dummy_appointment.serialize(), dummy_teos_sk),
    }


@responses.activate
def test_register():
    # Simulate a register response
    slots = 100
    expiry = CURRENT_HEIGHT + 4320
    signature = Cryptographer.sign(receipts.create_registration_receipt(dummy_user_id, slots, expiry), dummy_teos_sk)
    response = {"available_slots": slots, "subscription_expiry": expiry, "subscription_signature": signature}
    responses.add(responses.POST, register_endpoint, json=response, status=200)
    teos_client.register(dummy_user_id, dummy_teos_id, teos_url)


@responses.activate
def test_register_wrong_signature():
    # Simulate a register response with a wrong signature
    slots = 100
    expiry = CURRENT_HEIGHT + 4320
    signature = Cryptographer.sign(receipts.create_registration_receipt(dummy_user_id, slots, expiry), another_sk)
    response = {"available_slots": slots, "subscription_expiry": expiry, "subscription_signature": signature}
    responses.add(responses.POST, register_endpoint, json=response, status=200)

    with pytest.raises(TowerResponseError, match="signature is invalid"):
        teos_client.register(dummy_user_id, dummy_teos_id, teos_url)


@responses.activate
def test_register_no_signature():
    # Simulate a register response with a wrong signature
    slots = 100
    expiry = CURRENT_HEIGHT + 4320
    response = {"available_slots": slots, "subscription_expiry": expiry}
    responses.add(responses.POST, register_endpoint, json=response, status=200)

    with pytest.raises(TowerResponseError, match="does not contain the signature"):
        teos_client.register(dummy_user_id, dummy_teos_id, teos_url)


def test_register_with_invalid_user_id():
    # Simulate a register response
    with pytest.raises(InvalidParameter):
        teos_client.register("invalid_user_id", dummy_teos_id, teos_url)


def test_register_with_connection_error():
    # We don't mock any url to simulate a connection error
    with pytest.raises(ConnectionError):
        teos_client.register(dummy_user_id, dummy_teos_id, teos_url)

    # Should also fail with missing or unknown protocol, with a more specific error message
    with pytest.raises(ConnectionError, match="Invalid URL"):
        teos_client.register(dummy_user_id, dummy_teos_id, "//teos.watch")
    with pytest.raises(ConnectionError, match="Invalid URL"):
        teos_client.register(dummy_user_id, dummy_teos_id, "nonExistingProtocol://teos.watch")


def test_create_appointment():
    # Tests that an appointment is properly created provided the input data is correct
    appointment = teos_client.create_appointment(dummy_appointment_data)
    assert isinstance(appointment, Appointment)
    assert appointment.locator == dummy_appointment_data.get(
        "locator"
    ) and appointment.to_self_delay == dummy_appointment_data.get("to_self_delay")
    assert appointment.encrypted_blob == Cryptographer.encrypt(
        dummy_appointment_data.get("tx"), dummy_appointment_data.get("tx_id")
    )


def test_create_appointment_missing_fields():
    # Data is sanitized by parse_add_appointment_args, so the input must be a dict with data.
    # The expected fields may be missing though.
    no_txid = {"tx": get_random_value_hex(200)}
    no_tx = {"tx_id": get_random_value_hex(32)}
    incorrect_txid = {"tx_id": get_random_value_hex(31), "tx": get_random_value_hex(200)}
    incorrect_tx = {"tx_id": get_random_value_hex(32), "tx": 1}

    with pytest.raises(InvalidParameter, match="Missing tx_id"):
        teos_client.create_appointment(no_txid)
    with pytest.raises(InvalidParameter, match="Wrong tx_id"):
        teos_client.create_appointment(incorrect_txid)
    with pytest.raises(InvalidParameter, match="tx field is missing"):
        teos_client.create_appointment(no_tx)
    with pytest.raises(InvalidParameter, match="tx field is not a string"):
        teos_client.create_appointment(incorrect_tx)


@responses.activate
def test_add_appointment():
    # Simulate a request to add_appointment for dummy_appointment, make sure that the right endpoint is requested
    # and the return value is True
    appointment = teos_client.create_appointment(dummy_appointment_data)
    user_signature = Cryptographer.sign(appointment.serialize(), dummy_user_sk)
    appointment_receipt = receipts.create_appointment_receipt(user_signature, CURRENT_HEIGHT)

    response = {
        "locator": dummy_appointment.locator,
        "signature": Cryptographer.sign(appointment_receipt, dummy_teos_sk),
        "available_slots": 100,
        "start_block": CURRENT_HEIGHT,
        "subscription_expiry": CURRENT_HEIGHT + 4320,
    }
    responses.add(responses.POST, add_appointment_endpoint, json=response, status=200)

    result = teos_client.add_appointment(
        Appointment.from_dict(dummy_appointment_data), dummy_user_sk, dummy_teos_id, teos_url
    )

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == add_appointment_endpoint
    assert result


@responses.activate
def test_add_appointment_with_missing_signature():
    # Simulate a request to add_appointment for dummy_appointment, but the response does not have
    # the signature.

    appointment = teos_client.create_appointment(dummy_appointment_data)

    response = {
        "locator": dummy_appointment.locator,
        # no signature
        "available_slots": 100,
        "start_block": CURRENT_HEIGHT,
        "subscription_expiry": CURRENT_HEIGHT + 4320,
    }

    responses.add(responses.POST, add_appointment_endpoint, json=response, status=200)

    with pytest.raises(TowerResponseError, match="does not contain the signature"):
        teos_client.add_appointment(appointment, dummy_user_sk, dummy_teos_id, teos_url)

    # should have performed exactly 1 network request
    assert len(responses.calls) == 1


@responses.activate
def test_add_appointment_with_invalid_signature():
    # Simulate a request to add_appointment for dummy_appointment, but sign with a different key,
    # make sure that the right endpoint is requested, but the return value is False
    appointment = teos_client.create_appointment(dummy_appointment_data)
    user_signature = Cryptographer.sign(appointment.serialize(), dummy_user_sk)
    appointment_receipt = receipts.create_appointment_receipt(user_signature, CURRENT_HEIGHT)

    # Sign with a bad key
    response = {
        "locator": dummy_appointment.locator,
        "signature": Cryptographer.sign(appointment_receipt, another_sk),
        "available_slots": 100,
        "start_block": CURRENT_HEIGHT,
        "subscription_expiry": CURRENT_HEIGHT + 4320,
    }

    responses.add(responses.POST, add_appointment_endpoint, json=response, status=200)

    with pytest.raises(TowerResponseError):
        teos_client.add_appointment(
            Appointment.from_dict(dummy_appointment_data), dummy_user_sk, dummy_teos_id, teos_url
        )

    # should have performed exactly 1 network request
    assert len(responses.calls) == 1


@responses.activate
def test_get_appointment():
    # Response of get_appointment endpoint is an appointment with status added to it.
    response = {
        "locator": dummy_appointment_dict.get("locator"),
        "status": AppointmentStatus.BEING_WATCHED,
        "appointment": dummy_appointment_dict,
    }

    responses.add(responses.POST, get_appointment_endpoint, json=response, status=200)
    result = teos_client.get_appointment(dummy_appointment_dict.get("locator"), dummy_user_sk, dummy_teos_id, teos_url)

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == get_appointment_endpoint
    assert result.get("locator") == response.get("locator")


def test_get_appointment_invalid_locator():
    # Test that an invalid locator fails with InvalidParamater before any network request
    with pytest.raises(InvalidParameter, match="locator is not valid"):
        teos_client.get_appointment("deadbeef", dummy_user_sk, dummy_teos_id, teos_url)


@responses.activate
def test_get_appointment_tower_error():
    # Test that a TowerResponseError is raised if the response is invalid.
    locator = dummy_appointment_dict.get("locator")

    responses.add(responses.POST, get_appointment_endpoint, body="{ invalid json response", status=200)
    with pytest.raises(TowerResponseError):
        teos_client.get_appointment(locator, dummy_user_sk, dummy_teos_id, teos_url)

    assert len(responses.calls) == 1


@responses.activate
def test_get_appointment_connection_error():
    locator = get_random_value_hex(16)

    # Test that get_appointment handles a connection error appropriately.
    responses.add(responses.POST, get_appointment_endpoint, body=ConnectionError())

    with pytest.raises(ConnectionError):
        teos_client.get_appointment(locator, dummy_user_sk, dummy_teos_id, teos_url)


@responses.activate
def test_get_subscription_info():
    # Response of get_appointment endpoint is an appointment with status added to it.
    response = dummy_user_data

    responses.add(responses.POST, get_subscription_info_endpoint, json=response, status=200)
    result = teos_client.get_subscription_info(dummy_user_sk, dummy_teos_id, teos_url)

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == get_subscription_info_endpoint
    assert result.get("available_slots") == response.get("available_slots")


@responses.activate
def test_get_subscription_info_wrong_user_sk():
    responses.add(responses.POST, get_subscription_info_endpoint, body=TowerResponseError("Wrong signature"))

    with pytest.raises(TowerResponseError):
        teos_client.get_subscription_info(another_sk, dummy_teos_id, teos_url)


def test_load_keys(keyfiles):
    # Test that it correctly returns a tuple of 2 elements with the correct keys
    r = teos_client.load_keys(keyfiles.private_key_file_path)
    assert isinstance(r, tuple)
    assert len(r) == 2


def test_load_keys_none(keyfiles):
    # If the param does not match the expected, we should get an InvalidKey exception
    with pytest.raises(InvalidKey):
        teos_client.load_keys(None)


def test_load_keys_empty(keyfiles):
    # If the file is empty, InvalidKey should be raised
    with pytest.raises(InvalidKey):
        teos_client.load_keys(keyfiles.empty_file_path)


def test_load_teos_id(keyfiles):
    # Test that it correctly returns the teos id
    assert is_compressed_pk(teos_client.load_teos_id(keyfiles.public_key_file_path))


def test_load_teos_id_none(keyfiles):
    # If the param does not match the expected, we should get an InvalidKey exception
    with pytest.raises(InvalidKey, match="public key file not found"):
        teos_client.load_teos_id(None)


def test_load_teos_id_empty(keyfiles):
    # If the file is empty, InvalidKey should be raised
    with pytest.raises(InvalidKey, match="public key cannot be loaded"):
        teos_client.load_teos_id(keyfiles.empty_file_path)


@responses.activate
def test_post_request():
    response = {
        "locator": dummy_appointment.to_dict()["locator"],
        "signature": Cryptographer.sign(dummy_appointment.serialize(), dummy_teos_sk),
    }

    responses.add(responses.POST, add_appointment_endpoint, json=response, status=200)
    response = teos_client.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == add_appointment_endpoint
    assert response


def test_post_request_connection_error():
    with pytest.raises(ConnectionError):
        teos_client.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)


@responses.activate
def test_process_post_response(post_response):
    # A 200 OK with a correct json response should return the json of the response
    responses.add(responses.POST, add_appointment_endpoint, json=post_response, status=200)
    r = teos_client.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)
    assert teos_client.process_post_response(r) == r.json()


@responses.activate
def test_process_post_response_404(post_response):
    # If the response code is a rejection (lets say 404) it should raise TowerResponseError
    responses.add(responses.POST, add_appointment_endpoint, json=post_response, status=404)
    with pytest.raises(TowerResponseError):
        r = teos_client.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)
        teos_client.process_post_response(r)


@responses.activate
def test_process_post_response_not_json(post_response):
    # TowerResponseError should be raised if the response is not in json (independently of the status code)
    responses.add(responses.POST, add_appointment_endpoint, status=404)
    with pytest.raises(TowerResponseError):
        r = teos_client.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)
        teos_client.process_post_response(r)

    responses.replace(responses.POST, add_appointment_endpoint, status=200)
    with pytest.raises(TowerResponseError):
        r = teos_client.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)
        teos_client.process_post_response(r)


def test_parse_add_appointment_args():
    # If file exists and has data in it, function should work.
    with open("appt_test_file", "w") as f:
        json.dump(dummy_appointment_data, f)

    appt_data = teos_client.parse_add_appointment_args(["-f", "appt_test_file"])
    assert appt_data

    # If appointment json is passed in, function should work.
    appt_data = teos_client.parse_add_appointment_args([json.dumps(dummy_appointment_data)])
    assert appt_data

    os.remove("appt_test_file")


def test_parse_add_appointment_args_wrong():
    # If no args are passed, function should fail.
    with pytest.raises(InvalidParameter):
        teos_client.parse_add_appointment_args(None)

    # If the arg is an empty dict it should fail
    with pytest.raises(InvalidParameter):
        teos_client.parse_add_appointment_args({})

    # If file doesn't exist, function should fail.
    with pytest.raises(FileNotFoundError):
        teos_client.parse_add_appointment_args(["-f", "nonexistent_file"])


def test_save_appointment_receipt(monkeypatch):
    appointments_folder = "test_appointments_receipts"
    monkeypatch.setitem(config, "APPOINTMENTS_FOLDER_NAME", appointments_folder)
    config["APPOINTMENTS_FOLDER_NAME"] = appointments_folder

    # The functions creates a new directory if it does not exist
    assert not os.path.exists(appointments_folder)
    teos_client.save_appointment_receipt(
        dummy_appointment.to_dict(),
        Cryptographer.sign(dummy_appointment.serialize(), dummy_teos_sk),
        CURRENT_HEIGHT,
        config.get("APPOINTMENTS_FOLDER_NAME"),
    )
    assert os.path.exists(appointments_folder)

    # Check that the receipt has been saved by checking the file names
    files = os.listdir(appointments_folder)
    assert any([dummy_appointment.locator in f for f in files])

    shutil.rmtree(appointments_folder)
