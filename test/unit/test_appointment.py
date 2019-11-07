import json
from pytest import fixture

from pisa import c_logger
from pisa.appointment import Appointment
from pisa.encrypted_blob import EncryptedBlob
from test.unit.conftest import get_random_value_hex


c_logger.disabled = True

# Not much to test here, adding it for completeness
@fixture
def appointment_data():
    locator = get_random_value_hex(32)
    start_time = 100
    end_time = 120
    dispute_delta = 20
    encrypted_blob_data = get_random_value_hex(100)
    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    return locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function


def test_init_appointment(appointment_data):
    # The appointment has no checks whatsoever, since the inspector is the one taking care or that, and the only one
    # creating appointments.
    # DISCUSS: whether this makes sense by design or checks should be ported from the inspector to the appointment
    #          35-appointment-checks

    locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function = appointment_data

    appointment = Appointment(locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function)

    assert (
        locator == appointment.locator
        and start_time == appointment.start_time
        and end_time == appointment.end_time
        and EncryptedBlob(encrypted_blob_data) == appointment.encrypted_blob
        and cipher == appointment.cipher
        and dispute_delta == appointment.dispute_delta
        and hash_function == appointment.hash_function
    )


def test_to_dict(appointment_data):
    locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function = appointment_data
    appointment = Appointment(locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function)

    dict_appointment = appointment.to_dict()

    assert (
        locator == dict_appointment.get("locator")
        and start_time == dict_appointment.get("start_time")
        and end_time == dict_appointment.get("end_time")
        and dispute_delta == dict_appointment.get("dispute_delta")
        and cipher == dict_appointment.get("cipher")
        and hash_function == dict_appointment.get("hash_function")
        and encrypted_blob_data == dict_appointment.get("encrypted_blob")
    )


def test_to_json(appointment_data):
    locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function = appointment_data
    appointment = Appointment(locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function)

    dict_appointment = json.loads(appointment.to_json())

    assert (
        locator == dict_appointment.get("locator")
        and start_time == dict_appointment.get("start_time")
        and end_time == dict_appointment.get("end_time")
        and dispute_delta == dict_appointment.get("dispute_delta")
        and cipher == dict_appointment.get("cipher")
        and hash_function == dict_appointment.get("hash_function")
        and encrypted_blob_data == dict_appointment.get("encrypted_blob")
    )
