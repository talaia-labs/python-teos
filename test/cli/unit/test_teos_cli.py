import os
import json
import shutil
import pytest
import responses
from coincurve import PrivateKey
from requests.exceptions import ConnectionError, Timeout

from common.tools import compute_locator
from common.appointment import Appointment
from common.cryptographer import Cryptographer
from common.exceptions import InvalidParameter, InvalidKey

import cli.teos_cli as teos_cli
from cli.exceptions import TowerResponseError

from test.cli.unit.conftest import get_random_value_hex, get_config

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

dummy_appointment_data = {
    "tx": get_random_value_hex(192),
    "tx_id": get_random_value_hex(32),
    "start_time": 1500,
    "end_time": 50000,
    "to_self_delay": 200,
}

# This is the format appointment turns into once it hits "add_appointment"
dummy_appointment_dict = {
    "locator": compute_locator(dummy_appointment_data.get("tx_id")),
    "start_time": dummy_appointment_data.get("start_time"),
    "end_time": dummy_appointment_data.get("end_time"),
    "to_self_delay": dummy_appointment_data.get("to_self_delay"),
    "encrypted_blob": Cryptographer.encrypt(dummy_appointment_data.get("tx"), dummy_appointment_data.get("tx_id")),
}

dummy_appointment = Appointment.from_dict(dummy_appointment_dict)


def get_signature(message, sk):
    return Cryptographer.sign(message, sk)


# TODO: 90-add-more-add-appointment-tests
@responses.activate
def test_register():
    # Simulate a register response
    response = {"public_key": dummy_user_id, "available_slots": 100}
    responses.add(responses.POST, register_endpoint, json=response, status=200)
    result = teos_cli.register(dummy_user_id, teos_url)

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == register_endpoint
    assert result.get("public_key") == dummy_user_id and result.get("available_slots") == response.get(
        "available_slots"
    )


@responses.activate
def test_register_with_invalid_user_id():
    # Simulate a register response
    with pytest.raises(InvalidParameter):
        teos_cli.register("invalid_user_id", teos_url)

    # should not have done any network request
    assert len(responses.calls) == 0


@responses.activate
def test_register_with_connection_error():
    # We don't mock any url to simulate a connection error
    with pytest.raises(ConnectionError):
        teos_cli.register(dummy_user_id, teos_url)

    # Should also fail with missing or unknown protocol, with a more specific error message
    with pytest.raises(ConnectionError, match="Invalid URL"):
        teos_cli.register(dummy_user_id, "//teos.watch")
    with pytest.raises(ConnectionError, match="Invalid URL"):
        teos_cli.register(dummy_user_id, "nonExistingProtocol://teos.watch")


@responses.activate
def test_add_appointment():
    # Simulate a request to add_appointment for dummy_appointment, make sure that the right endpoint is requested
    # and the return value is True
    response = {
        "locator": dummy_appointment.locator,
        "signature": get_signature(dummy_appointment.serialize(), dummy_teos_sk),
        "available_slots": 100,
    }
    responses.add(responses.POST, add_appointment_endpoint, json=response, status=200)
    result = teos_cli.add_appointment(dummy_appointment_data, dummy_user_sk, dummy_teos_id, teos_url)

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == add_appointment_endpoint
    assert result


@responses.activate
def test_add_appointment_with_invalid_appointment_data(monkeypatch):
    with pytest.raises(InvalidParameter, match="JSON is empty"):
        teos_cli.add_appointment("", dummy_user_sk, dummy_teos_id, teos_url)

    with monkeypatch.context() as m:
        with pytest.raises(InvalidParameter, match="locator is wrong"):
            m.setitem(dummy_appointment_data, "tx_id", "invalid_txid")
            teos_cli.add_appointment(dummy_appointment_data, dummy_user_sk, dummy_teos_id, teos_url)

    with monkeypatch.context() as m:
        with pytest.raises(InvalidParameter, match="missing the transaction"):
            m.setitem(dummy_appointment_data, "tx", "")
            teos_cli.add_appointment(dummy_appointment_data, dummy_user_sk, dummy_teos_id, teos_url)

    # None of the previous calls should have performed any network request
    assert len(responses.calls) == 0


@responses.activate
def test_add_appointment_with_missing_signature():
    # Simulate a request to add_appointment for dummy_appointment, but the response does not have
    # the signature.

    response = {
        "locator": dummy_appointment.to_dict()["locator"],
        # no signature
        "available_slots": 100,
    }

    responses.add(responses.POST, add_appointment_endpoint, json=response, status=200)

    with pytest.raises(TowerResponseError, match="does not contain the signature"):
        teos_cli.add_appointment(dummy_appointment_data, dummy_user_sk, dummy_teos_id, teos_url)

    # should have performed exactly 1 network request
    assert len(responses.calls) == 1


@responses.activate
def test_add_appointment_with_invalid_signature():
    # Simulate a request to add_appointment for dummy_appointment, but sign with a different key,
    # make sure that the right endpoint is requested, but the return value is False

    response = {
        "locator": dummy_appointment.to_dict()["locator"],
        "signature": get_signature(dummy_appointment.serialize(), another_sk),  # Sign with a bad key
        "available_slots": 100,
    }

    responses.add(responses.POST, add_appointment_endpoint, json=response, status=200)

    with pytest.raises(TowerResponseError):
        teos_cli.add_appointment(dummy_appointment_data, dummy_user_sk, dummy_teos_id, teos_url)

    # should have performed exactly 1 network request
    assert len(responses.calls) == 1


@responses.activate
def test_get_appointment():
    # Response of get_appointment endpoint is an appointment with status added to it.
    response = {
        "locator": dummy_appointment_dict.get("locator"),
        "status": "being_watched",
        "appointment": dummy_appointment_dict,
    }

    responses.add(responses.POST, get_appointment_endpoint, json=response, status=200)
    result = teos_cli.get_appointment(dummy_appointment_dict.get("locator"), dummy_user_sk, dummy_teos_id, teos_url)

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == get_appointment_endpoint
    assert result.get("locator") == response.get("locator")


@responses.activate
def test_get_appointment_invalid_locator():
    with pytest.raises(InvalidParameter, match="locator is not valid"):
        teos_cli.get_appointment("deadbeef", dummy_user_sk, dummy_teos_id, teos_url)

    # Should fail validation before making any network request
    assert len(responses.calls) == 0


@responses.activate
def test_get_appointment_tower_error():
    locator = dummy_appointment_dict.get("locator")

    responses.add(responses.POST, get_appointment_endpoint, body="{ invalid json response", status=200)
    with pytest.raises(TowerResponseError):
        teos_cli.get_appointment(locator, dummy_user_sk, dummy_teos_id, teos_url)


@responses.activate
def test_get_appointment_connection_error():
    locator = get_random_value_hex(16)

    # Test that get_appointment handles a connection error appropriately.
    responses.add(responses.POST, get_appointment_endpoint, body=ConnectionError())

    with pytest.raises(ConnectionError):
        teos_cli.get_appointment(locator, dummy_user_sk, dummy_teos_id, teos_url)


def test_load_keys():
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

    # Now we can test the function passing the using this files
    r = teos_cli.load_keys(public_key_file_path, private_key_file_path)
    assert isinstance(r, tuple)
    assert len(r) == 3

    # If any param does not match the expected, we should get an InvalidKey exception
    with pytest.raises(InvalidKey):
        teos_cli.load_keys(None, private_key_file_path)
    with pytest.raises(InvalidKey):
        teos_cli.load_keys(public_key_file_path, None)

    # The same should happen if we pass a public key where a private should be, for instance
    with pytest.raises(InvalidKey):
        teos_cli.load_keys(private_key_file_path, public_key_file_path)

    # Same if any of the files is empty
    with pytest.raises(InvalidKey):
        teos_cli.load_keys(empty_file_path, private_key_file_path)
    with pytest.raises(InvalidKey):
        teos_cli.load_keys(public_key_file_path, empty_file_path)

    # Remove the tmp files
    os.remove(private_key_file_path)
    os.remove(public_key_file_path)
    os.remove(empty_file_path)


@responses.activate
def test_post_request():
    response = {
        "locator": dummy_appointment.to_dict()["locator"],
        "signature": get_signature(dummy_appointment.serialize(), dummy_teos_sk),
    }

    responses.add(responses.POST, add_appointment_endpoint, json=response, status=200)
    response = teos_cli.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == add_appointment_endpoint
    assert response


@responses.activate
def test_process_post_response():
    # Let's first create a response
    response = {
        "locator": dummy_appointment.to_dict()["locator"],
        "signature": get_signature(dummy_appointment.serialize(), dummy_teos_sk),
    }

    # A 200 OK with a correct json response should return the json of the response
    responses.add(responses.POST, add_appointment_endpoint, json=response, status=200)
    r = teos_cli.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)
    assert teos_cli.process_post_response(r) == r.json()

    # If we modify the response code for a rejection (lets say 404) we should get None
    responses.replace(responses.POST, add_appointment_endpoint, json=response, status=404)
    with pytest.raises(TowerResponseError):
        r = teos_cli.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)
        teos_cli.process_post_response(r)

    # The same should happen if the response is not in json independently of the return type
    responses.replace(responses.POST, add_appointment_endpoint, status=404)
    with pytest.raises(TowerResponseError):
        r = teos_cli.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)
        teos_cli.process_post_response(r)

    responses.replace(responses.POST, add_appointment_endpoint, status=200)
    with pytest.raises(TowerResponseError):
        r = teos_cli.post_request(json.dumps(dummy_appointment_data), add_appointment_endpoint)
        teos_cli.process_post_response(r)


def test_parse_add_appointment_args():
    # If file exists and has data in it, function should work.
    with open("appt_test_file", "w") as f:
        json.dump(dummy_appointment_data, f)

    appt_data = teos_cli.parse_add_appointment_args(["-f", "appt_test_file"])
    assert appt_data

    # If appointment json is passed in, function should work.
    appt_data = teos_cli.parse_add_appointment_args([json.dumps(dummy_appointment_data)])
    assert appt_data

    os.remove("appt_test_file")


def test_parse_add_appointment_args_wrong():
    # If no args are passed, function should fail.
    with pytest.raises(InvalidParameter):
        teos_cli.parse_add_appointment_args(None)

    # If file doesn't exist, function should fail.
    with pytest.raises(FileNotFoundError):
        teos_cli.parse_add_appointment_args(["-f", "nonexistent_file"])


def test_save_appointment_receipt():
    appointments_folder = "test_appointments_receipts"
    config["APPOINTMENTS_FOLDER_NAME"] = appointments_folder

    # The functions creates a new directory if it does not exist
    assert not os.path.exists(appointments_folder)
    teos_cli.save_appointment_receipt(
        dummy_appointment.to_dict(),
        get_signature(dummy_appointment.serialize(), dummy_teos_sk),
        config.get("APPOINTMENTS_FOLDER_NAME"),
    )
    assert os.path.exists(appointments_folder)

    # Check that the receipt has been saved by checking the file names
    files = os.listdir(appointments_folder)
    assert any([dummy_appointment.locator in f for f in files])

    shutil.rmtree(appointments_folder)


@responses.activate
def test_get_all_appointments():
    # Response of get_all_appointments endpoint is all appointments from watcher and responder.
    dummy_appointment_dict["status"] = "being_watched"
    response = {"watcher_appointments": dummy_appointment_dict, "responder_trackers": {}}

    request_url = get_all_appointments_endpoint
    responses.add(responses.GET, request_url, json=response, status=200)
    result = teos_cli.get_all_appointments(teos_url)

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == request_url
    assert json.loads(result).get("locator") == response.get("locator")


@responses.activate
def test_get_all_appointments_err():
    # Test that get_all_appointments handles a connection error appropriately.
    request_url = get_all_appointments_endpoint
    responses.add(responses.GET, request_url, body=ConnectionError())

    assert not teos_cli.get_all_appointments(teos_url)

    # Test that get_all_appointments handles a timeout error appropriately.
    responses.replace(responses.GET, request_url, body=Timeout())

    assert not teos_cli.get_all_appointments(teos_url)

    # Test that get_all_appointments handles a 404 error appropriately.
    responses.replace(responses.GET, request_url, status=404)

    assert teos_cli.get_all_appointments(teos_url) is None
