import struct
import pytest
import binascii
import pyzbase32
from pytest import fixture
from coincurve import PrivateKey

from common.appointment import Appointment
from common.cryptographer import Cryptographer
from common.constants import LOCATOR_LEN_BYTES

from test.common.unit.conftest import get_random_value_hex


# Not much to test here, adding it for completeness
@fixture
def appointment_data():
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    start_time = 100
    end_time = 120
    to_self_delay = 20
    encrypted_blob_data = get_random_value_hex(100)

    return {
        "locator": locator,
        "start_time": start_time,
        "end_time": end_time,
        "to_self_delay": to_self_delay,
        "encrypted_blob": encrypted_blob_data,
    }


def test_init_appointment(appointment_data):
    # The appointment has no checks whatsoever, since the inspector is the one taking care or that, and the only one
    # creating appointments.
    appointment = Appointment(
        appointment_data["locator"], appointment_data["encrypted_blob"], appointment_data["to_self_delay"]
    )

    assert (
        appointment_data["locator"] == appointment.locator
        and appointment_data["to_self_delay"] == appointment.to_self_delay
        and appointment_data["encrypted_blob"] == appointment.encrypted_blob
    )


def test_to_dict(appointment_data):
    appointment = Appointment(
        appointment_data["locator"], appointment_data["encrypted_blob"], appointment_data["to_self_delay"]
    )

    dict_appointment = appointment.to_dict()

    assert (
        appointment_data["locator"] == dict_appointment["locator"]
        and appointment_data["to_self_delay"] == dict_appointment["to_self_delay"]
        and appointment_data["encrypted_blob"] == dict_appointment["encrypted_blob"]
    )


def test_from_dict(appointment_data):
    # The appointment should be build if we don't miss any field
    appointment = Appointment.from_dict(appointment_data)
    assert isinstance(appointment, Appointment)

    # Otherwise it should fail
    for key in appointment_data.keys():
        prev_val = appointment_data[key]
        appointment_data[key] = None

        with pytest.raises(ValueError, match="Wrong appointment data"):
            Appointment.from_dict(appointment_data)
            appointment_data[key] = prev_val


def test_serialize(appointment_data):
    # From the tower end, appointments are only created if they pass the inspector tests, so not covering weird formats.
    # Serialize may fail if, from the user end, the user tries to do it with an weird appointment. Not critical.

    appointment = Appointment.from_dict(appointment_data)
    serialized_appointment = appointment.serialize()

    # Size must be 16 + len(encrypted_blob) + 4
    assert len(serialized_appointment) >= 20
    assert isinstance(serialized_appointment, bytes)

    locator = serialized_appointment[:16]
    encrypted_blob = serialized_appointment[16:-4]
    to_self_delay = serialized_appointment[-4:]

    assert binascii.hexlify(locator).decode() == appointment.locator
    assert binascii.hexlify(encrypted_blob).decode() == appointment.encrypted_blob
    assert struct.unpack(">I", to_self_delay)[0] == appointment.to_self_delay


def test_create_receipt(appointment_data):
    # Not much to test here, basically making sure the fields are in the correct order
    # The receipt format is user_signature | start_block
    sk = PrivateKey.from_int(42)
    data = get_random_value_hex(120)
    signature = Cryptographer.sign(data.encode(), sk)
    start_block = 200
    receipt = Appointment.create_receipt(signature, start_block)

    assert pyzbase32.encode_bytes(receipt[:-4]).decode() == signature
    assert struct.unpack(">I", receipt[-4:])[0] == start_block
