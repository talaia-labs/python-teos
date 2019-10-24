import pytest
import responses
import requests
import json
from binascii import hexlify

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

import apps.cli.pisa_cli as pisa_cli
from apps.cli import PISA_PUBLIC_KEY

# TODO: should find a way of doing without this
from apps.cli.pisa_cli import build_appointment

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
    "tx": "01000000018c8414a5c6b39130304af37b8d053c6b225df525877e5e0cf73a147f2c2edcdb0100000000ffffffff01f82a0000000000001976a9146fe8102ebe0fccb56de43ec82601ba16c68496af88ac00000000",
    "tx_id": "dbdc2e2c7f143af70c5e7e8725f55d226b3c058d7bf34a303091b3c6a514848c",
    "start_time": 1500,
    "end_time": 50000,
    "dispute_delta": 200
}
dummy_appointment = build_appointment(**dummy_appointment_request)


def sign_appointment(sk, appointment):
    data = json.dumps(appointment, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hexlify(sk.sign(data, ec.ECDSA(hashes.SHA256()))).decode('utf-8')


def test_is_appointment_signature_valid():
    # Verify that an appointment signed by Pisa is valid
    signature = sign_appointment(pisa_sk, dummy_appointment)
    assert pisa_cli.is_appointment_signature_valid(dummy_appointment, signature)

    # Test that a signature from a different key is indeed invalid
    other_signature = sign_appointment(other_sk, dummy_appointment)
    assert not pisa_cli.is_appointment_signature_valid(dummy_appointment, other_signature)


@responses.activate
def test_add_appointment():
    response = {
        'locator': dummy_appointment['locator'],
        'signature': sign_appointment(pisa_sk, dummy_appointment)
    }

    request_url = 'http://{}/'.format(pisa_endpoint)
    responses.add(responses.POST, request_url, json=response, status=200)

    pisa_cli.add_appointment([json.dumps(dummy_appointment_request)])

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == request_url
