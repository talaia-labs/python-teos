import responses
import json
from binascii import hexlify

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

import apps.cli.pisa_cli as pisa_cli
from test.unit.conftest import get_random_value_hex

# TODO: should find a way of doing without this
from apps.cli.pisa_cli import build_appointment

# dummy keys for the tests
pisa_sk = ec.generate_private_key(ec.SECP256K1, default_backend())
pisa_pk = pisa_sk.public_key()

other_sk = ec.generate_private_key(ec.SECP256K1, default_backend())

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
    "dispute_delta": 200,
}
dummy_appointment = build_appointment(**dummy_appointment_request)

# FIXME: USE CRYPTOGRAPHER


def sign_appointment(sk, appointment):
    data = json.dumps(appointment, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hexlify(sk.sign(data, ec.ECDSA(hashes.SHA256()))).decode("utf-8")


def get_dummy_pisa_pk(der_data):
    return pisa_pk


@responses.activate
def test_add_appointment(monkeypatch):
    # Simulate a request to add_appointment for dummy_appointment, make sure that the right endpoint is requested
    # and the return value is True

    # make sure the test uses the right dummy key instead of loading it from disk
    monkeypatch.setattr(pisa_cli, "load_public_key", get_dummy_pisa_pk)

    response = {"locator": dummy_appointment["locator"], "signature": sign_appointment(pisa_sk, dummy_appointment)}

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

    # make sure the test uses the right dummy key instead of loading it from disk
    monkeypatch.setattr(pisa_cli, "load_public_key", get_dummy_pisa_pk)

    response = {
        "locator": dummy_appointment["locator"],
        "signature": sign_appointment(other_sk, dummy_appointment),  # signing with a different key
    }

    request_url = "http://{}/".format(pisa_endpoint)
    responses.add(responses.POST, request_url, json=response, status=200)

    result = pisa_cli.add_appointment([json.dumps(dummy_appointment_request)])

    assert not result
