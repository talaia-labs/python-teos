import struct
import pytest
import pyzbase32
from coincurve import PrivateKey

from common import receipts as receipts
from common.cryptographer import Cryptographer
from common.exceptions import InvalidParameter

from test.common.unit.conftest import get_random_value_hex


def test_create_registration_receipt():
    # Not much to test here, basically making sure the fields are in the correct order
    # The receipt format is user_id | available_slots | subscription_expiry

    user_id = "02" + get_random_value_hex(32)
    available_slots = 100
    subscription_expiry = 4320

    registration_receipt = receipts.create_registration_receipt(user_id, available_slots, subscription_expiry)

    assert registration_receipt[:33].hex() == user_id
    assert int.from_bytes(registration_receipt[33:37], "big") == available_slots
    assert int.from_bytes(registration_receipt[37:], "big") == subscription_expiry


def test_create_registration_receipt_wrong_inputs():
    user_id = "02" + get_random_value_hex(32)
    available_slots = 100
    subscription_expiry = 4320

    wrong_user_ids = ["01" + get_random_value_hex(32), "04" + get_random_value_hex(31), "06" + get_random_value_hex(33)]
    no_int = [{}, object, "", [], 3.4, None]
    overflow_iu4nt = pow(2, 32)

    for wrong_param in wrong_user_ids + no_int:
        with pytest.raises(InvalidParameter, match="public key does not match expected format"):
            receipts.create_registration_receipt(wrong_param, available_slots, subscription_expiry)
        with pytest.raises(InvalidParameter, match="available_slots must be a 4-byte unsigned integer"):
            receipts.create_registration_receipt(user_id, wrong_param, subscription_expiry)
        with pytest.raises(InvalidParameter, match="subscription_expiry must be a 4-byte unsigned integer"):
            receipts.create_registration_receipt(user_id, available_slots, wrong_param)

    # Same for overflow u4int
    with pytest.raises(InvalidParameter, match="available_slots must be a 4-byte unsigned integer"):
        receipts.create_registration_receipt(user_id, overflow_iu4nt, subscription_expiry)
    with pytest.raises(InvalidParameter, match="subscription_expiry must be a 4-byte unsigned integer"):
        receipts.create_registration_receipt(user_id, available_slots, overflow_iu4nt)


def test_create_appointment_receipt(appointment_data):
    # Not much to test here, basically making sure the fields are in the correct order
    # The receipt format is user_signature | start_block
    sk = PrivateKey.from_int(42)
    data = get_random_value_hex(120)
    signature = Cryptographer.sign(data.encode(), sk)
    start_block = 200

    receipt = receipts.create_appointment_receipt(signature, start_block)

    assert pyzbase32.encode_bytes(receipt[:-4]).decode() == signature
    assert struct.unpack(">I", receipt[-4:])[0] == start_block


def test_create_appointment_receipt_wrong_inputs():
    sk = PrivateKey.from_int(42)
    data = get_random_value_hex(120)
    signature = Cryptographer.sign(data.encode(), sk)
    start_block = 200
    overflow_iu4nt = pow(2, 32)

    no_str = [{}, [], None, 15, 4.5, dict(), object, True]
    no_int = [{}, [], None, "", 4.5, dict(), object]

    for wrong_param in no_str:
        with pytest.raises(InvalidParameter, match="user_signature is invalid"):
            receipts.create_appointment_receipt(wrong_param, start_block)
    for wrong_param in no_int:
        with pytest.raises(InvalidParameter, match="must be a 4-byte unsigned integer"):
            receipts.create_appointment_receipt(signature, wrong_param)

    # Same for overflow u4int
    with pytest.raises(InvalidParameter, match="start_block must be a 4-byte unsigned integer"):
        receipts.create_appointment_receipt(signature, overflow_iu4nt)
