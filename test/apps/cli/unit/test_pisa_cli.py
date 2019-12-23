import responses
import json
import os
import pytest
from binascii import hexlify

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from common.appointment import Appointment
from common.cryptographer import Cryptographer

import apps.cli.pisa_cli as pisa_cli
from test.apps.cli.unit.conftest import get_random_value_hex

# dummy keys for the tests
pisa_sk = ec.generate_private_key(ec.SECP256K1, default_backend())
pisa_pk = pisa_sk.public_key()

other_sk = ec.generate_private_key(ec.SECP256K1, default_backend())

pisa_sk_der = pisa_sk.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
)
pisa_pk_der = pisa_pk.public_bytes(
    encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo
)

other_sk_der = other_sk.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
)


# Replace the key in the module with a key we control for the tests
pisa_cli.pisa_public_key = pisa_pk
# Replace endpoint with dummy one
pisa_cli.pisa_api_server = "dummy.com"
pisa_cli.pisa_api_port = 12345
pisa_endpoint = pisa_cli.pisa_api_server + ":" + str(pisa_cli.pisa_api_port)

dummy_appointment_request = {
    "tx": get_random_value_hex(192),
    "tx_id": get_random_value_hex(32),
    "start_time": 1500,
    "end_time": 50000,
    "to_self_delay": 200,
    "encrypted_blob": get_random_value_hex(120),
}

# This is the format appointment turns into once it hits "add_appointment"
dummy_appointment_full = {
    "locator": get_random_value_hex(32),
    "start_time": 1500,
    "end_time": 50000,
    "to_self_delay": 200,
    "encrypted_blob": get_random_value_hex(120),
}

dummy_appointment = Appointment.from_dict(dummy_appointment_full)


def get_dummy_pisa_sk_der(*args):
    return pisa_sk_der


def get_dummy_pisa_pk_der(*args):
    return pisa_pk_der


def get_dummy_hex_pk_der(*args):
    return hexlify(get_dummy_pisa_pk_der(None))


def get_dummy_signature(*args):
    sk = Cryptographer.load_private_key_der(pisa_sk_der)
    return Cryptographer.sign(dummy_appointment.serialize(), sk)


def get_bad_signature(*args):
    sk = Cryptographer.load_private_key_der(other_sk_der)
    return Cryptographer.sign(dummy_appointment.serialize(), sk)


def valid_sig(*args):
    return True


def invalid_sig(*args):
    return False


@responses.activate
def test_add_appointment(monkeypatch):
    # Simulate a request to add_appointment for dummy_appointment, make sure that the right endpoint is requested
    # and the return value is True

    # Make sure the test uses the dummy signature
    monkeypatch.setattr(pisa_cli, "get_appointment_signature", get_dummy_signature)
    monkeypatch.setattr(pisa_cli, "get_pk", get_dummy_hex_pk_der)
    monkeypatch.setattr(pisa_cli, "check_signature", valid_sig)

    response = {"locator": dummy_appointment.to_dict()["locator"], "signature": get_dummy_signature(None)}

    request_url = "http://{}/".format(pisa_endpoint)
    responses.add(responses.POST, request_url, json=response, status=200)

    result = pisa_cli.add_appointment([json.dumps(dummy_appointment_request)])

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == request_url

    assert result


@responses.activate
def test_add_appointment_with_invalid_signature(monkeypatch):
    # Simulate a request to add_appointment for dummy_appointment, but sign with a different key,
    # make sure that the right endpoint is requested, but the return value is False

    # Make sure the test uses the bad dummy signature
    monkeypatch.setattr(pisa_cli, "get_appointment_signature", get_bad_signature)
    monkeypatch.setattr(pisa_cli, "get_pk", get_dummy_hex_pk_der)
    monkeypatch.setattr(pisa_cli, "check_signature", invalid_sig)

    response = {
        "locator": dummy_appointment.to_dict()["locator"],
        "signature": get_bad_signature(None),  # Sign with a bad key
    }

    request_url = "http://{}/".format(pisa_endpoint)
    responses.add(responses.POST, request_url, json=response, status=200)

    result = pisa_cli.add_appointment([json.dumps(dummy_appointment_request)])

    assert not result


def test_parse_add_appointment_args():
    # If no args are passed, function should fail.
    appt_data = pisa_cli.parse_add_appointment_args(None)
    assert not appt_data

    # If file doesn't exist, function should fail.
    appt_data = pisa_cli.parse_add_appointment_args(["-f", "nonexistent_file"])
    assert not appt_data

    # If file exists and has data in it, function should work.
    with open("appt_test_file", "w") as f:
        json.dump(dummy_appointment_request, f)

    appt_data = pisa_cli.parse_add_appointment_args(["-f", "appt_test_file"])
    assert appt_data

    os.remove("appt_test_file")

    # If appointment json is passed in, funcion should work.
    appt_data = pisa_cli.parse_add_appointment_args([json.dumps(dummy_appointment_request)])
    assert appt_data


@responses.activate
def test_post_data_to_add_appointment_endpoint():
    response = {
        "locator": dummy_appointment.to_dict()["locator"],
        "signature": Cryptographer.sign(dummy_appointment.serialize(), pisa_sk),
    }

    request_url = "http://{}/".format(pisa_endpoint)
    responses.add(responses.POST, request_url, json=response, status=200)

    response = pisa_cli.post_data_to_add_appointment_endpoint(request_url, json.dumps(dummy_appointment_request))

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == request_url

    assert response


def test_check_signature(monkeypatch):
    # Make sure the test uses the right dummy key instead of loading it from disk
    monkeypatch.setattr(pisa_cli, "load_key_file_data", get_dummy_pisa_pk_der)

    valid = pisa_cli.check_signature(get_dummy_signature(), dummy_appointment)

    assert valid

    valid = pisa_cli.check_signature(get_bad_signature(), dummy_appointment)

    assert not valid


def test_get_appointment_signature(monkeypatch):
    # Make sure the test uses the right dummy key instead of loading it from disk
    monkeypatch.setattr(pisa_cli, "load_key_file_data", get_dummy_pisa_sk_der)

    signature = pisa_cli.get_appointment_signature(dummy_appointment)

    assert isinstance(signature, str)


def test_get_pk(monkeypatch):
    # Make sure the test uses the right dummy key instead of loading it from disk
    monkeypatch.setattr(pisa_cli, "load_key_file_data", get_dummy_pisa_pk_der)

    pk = pisa_cli.get_pk()

    assert isinstance(pk, bytes)
