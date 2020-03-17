import os
import json
import shutil
import responses
from coincurve import PrivateKey

import common.cryptographer
from common.logger import Logger
from common.tools import compute_locator
from common.appointment import Appointment
from common.cryptographer import Cryptographer

from common.blob import Blob
import apps.cli.teos_cli as teos_cli
from test.apps.cli.unit.conftest import get_random_value_hex

common.cryptographer.logger = Logger(actor="Cryptographer", log_name_prefix=teos_cli.LOG_PREFIX)

# dummy keys for the tests
dummy_sk = PrivateKey()
dummy_pk = dummy_sk.public_key
another_sk = PrivateKey()


# Replace the key in the module with a key we control for the tests
teos_cli.teos_public_key = dummy_pk
# Replace endpoint with dummy one
teos_cli.teos_api_server = "https://dummy.com"
teos_cli.teos_api_port = 12345
teos_endpoint = "{}:{}/".format(teos_cli.teos_api_server, teos_cli.teos_api_port)

dummy_appointment_request = {
    "tx": get_random_value_hex(192),
    "tx_id": get_random_value_hex(32),
    "start_time": 1500,
    "end_time": 50000,
    "to_self_delay": 200,
}

# This is the format appointment turns into once it hits "add_appointment"
dummy_appointment_full = {
    "locator": compute_locator(dummy_appointment_request.get("tx_id")),
    "start_time": dummy_appointment_request.get("start_time"),
    "end_time": dummy_appointment_request.get("end_time"),
    "to_self_delay": dummy_appointment_request.get("to_self_delay"),
    "encrypted_blob": Cryptographer.encrypt(
        Blob(dummy_appointment_request.get("tx")), dummy_appointment_request.get("tx_id")
    ),
}

dummy_appointment = Appointment.from_dict(dummy_appointment_full)


def load_dummy_keys(*args):
    return dummy_pk, dummy_sk, dummy_pk.format(compressed=True)


def get_dummy_signature(*args):
    return Cryptographer.sign(dummy_appointment.serialize(), dummy_sk)


def get_bad_signature(*args):
    return Cryptographer.sign(dummy_appointment.serialize(), another_sk)


def test_load_keys():
    # Let's first create a private key and public key files
    private_key_file_path = "sk_test_file"
    public_key_file_path = "pk_test_file"
    empty_file_path = "empty_file"
    with open(private_key_file_path, "wb") as f:
        f.write(dummy_sk.to_der())
    with open(public_key_file_path, "wb") as f:
        f.write(dummy_pk.format(compressed=True))
    with open(empty_file_path, "wb") as f:
        pass

    # Now we can test the function passing the using this files (we'll use the same pk for both)
    r = teos_cli.load_keys(public_key_file_path, private_key_file_path, public_key_file_path)
    assert isinstance(r, tuple)
    assert len(r) == 3

    # If any param does not match we should get None as result
    assert teos_cli.load_keys(None, private_key_file_path, public_key_file_path) is None
    assert teos_cli.load_keys(public_key_file_path, None, public_key_file_path) is None
    assert teos_cli.load_keys(public_key_file_path, private_key_file_path, None) is None

    # The same should happen if we pass a public key where a private should be, for instance
    assert teos_cli.load_keys(private_key_file_path, public_key_file_path, private_key_file_path) is None

    # Same if any of the files is empty
    assert teos_cli.load_keys(empty_file_path, private_key_file_path, public_key_file_path) is None
    assert teos_cli.load_keys(public_key_file_path, empty_file_path, public_key_file_path) is None
    assert teos_cli.load_keys(public_key_file_path, private_key_file_path, empty_file_path) is None

    os.remove(private_key_file_path)
    os.remove(public_key_file_path)
    os.remove(empty_file_path)


# TODO: 90-add-more-add-appointment-tests
@responses.activate
def test_add_appointment(monkeypatch):
    # Simulate a request to add_appointment for dummy_appointment, make sure that the right endpoint is requested
    # and the return value is True
    monkeypatch.setattr(teos_cli, "load_keys", load_dummy_keys)

    response = {"locator": dummy_appointment.locator, "signature": get_dummy_signature()}
    responses.add(responses.POST, teos_endpoint, json=response, status=200)
    result = teos_cli.add_appointment([json.dumps(dummy_appointment_request)])

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == teos_endpoint
    assert result


@responses.activate
def test_add_appointment_with_invalid_signature(monkeypatch):
    # Simulate a request to add_appointment for dummy_appointment, but sign with a different key,
    # make sure that the right endpoint is requested, but the return value is False

    # Make sure the test uses the bad dummy signature
    monkeypatch.setattr(teos_cli, "load_keys", load_dummy_keys)

    response = {
        "locator": dummy_appointment.to_dict()["locator"],
        "signature": get_bad_signature(),  # Sign with a bad key
    }

    responses.add(responses.POST, teos_endpoint, json=response, status=200)
    result = teos_cli.add_appointment([json.dumps(dummy_appointment_request)])

    assert result is False


def test_parse_add_appointment_args():
    # If no args are passed, function should fail.
    appt_data = teos_cli.parse_add_appointment_args(None)
    assert not appt_data

    # If file doesn't exist, function should fail.
    appt_data = teos_cli.parse_add_appointment_args(["-f", "nonexistent_file"])
    assert not appt_data

    # If file exists and has data in it, function should work.
    with open("appt_test_file", "w") as f:
        json.dump(dummy_appointment_request, f)

    appt_data = teos_cli.parse_add_appointment_args(["-f", "appt_test_file"])
    assert appt_data

    os.remove("appt_test_file")

    # If appointment json is passed in, function should work.
    appt_data = teos_cli.parse_add_appointment_args([json.dumps(dummy_appointment_request)])
    assert appt_data


@responses.activate
def test_post_appointment():
    response = {
        "locator": dummy_appointment.to_dict()["locator"],
        "signature": Cryptographer.sign(dummy_appointment.serialize(), dummy_pk),
    }

    responses.add(responses.POST, teos_endpoint, json=response, status=200)
    response = teos_cli.post_appointment(json.dumps(dummy_appointment_request))

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == teos_endpoint
    assert response


@responses.activate
def test_process_post_appointment_response():
    # Let's first crete a response
    response = {
        "locator": dummy_appointment.to_dict()["locator"],
        "signature": Cryptographer.sign(dummy_appointment.serialize(), dummy_pk),
    }

    # A 200 OK with a correct json response should return the json of the response
    responses.add(responses.POST, teos_endpoint, json=response, status=200)
    r = teos_cli.post_appointment(json.dumps(dummy_appointment_request))
    assert teos_cli.process_post_appointment_response(r) == r.json()

    # If we modify the response code tor a rejection (lets say 404) we should get None
    responses.replace(responses.POST, teos_endpoint, json=response, status=404)
    r = teos_cli.post_appointment(json.dumps(dummy_appointment_request))
    assert teos_cli.process_post_appointment_response(r) is None

    # The same should happen if the response is not in json
    responses.replace(responses.POST, teos_endpoint, status=404)
    r = teos_cli.post_appointment(json.dumps(dummy_appointment_request))
    assert teos_cli.process_post_appointment_response(r) is None


def test_save_appointment_receipt(monkeypatch):
    appointments_folder = "test_appointments_receipts"
    teos_cli.config["APPOINTMENTS_FOLDER_NAME"] = appointments_folder

    # The functions creates a new directory if it does not exist
    assert not os.path.exists(appointments_folder)
    teos_cli.save_appointment_receipt(dummy_appointment.to_dict(), get_dummy_signature())
    assert os.path.exists(appointments_folder)

    # Check that the receipt has been saved by checking the file names
    files = os.listdir(appointments_folder)
    assert any([dummy_appointment.locator in f for f in files])

    shutil.rmtree(appointments_folder)


@responses.activate
def test_get_appointment():
    # Response of get_appointment endpoint is an appointment with status added to it.
    dummy_appointment_full["status"] = "being_watched"
    response = dummy_appointment_full

    request_url = "{}get_appointment?locator={}".format(teos_endpoint, response.get("locator"))
    responses.add(responses.GET, request_url, json=response, status=200)
    result = teos_cli.get_appointment(response.get("locator"))

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == request_url
    assert result.get("locator") == response.get("locator")


@responses.activate
def test_get_appointment_err():
    locator = get_random_value_hex(16)

    # Test that get_appointment handles a connection error appropriately.
    request_url = "{}get_appointment?locator=".format(teos_endpoint, locator)
    responses.add(responses.GET, request_url, body=ConnectionError())

    assert not teos_cli.get_appointment(locator)
