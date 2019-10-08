from os import urandom
from pytest import fixture

from pisa.appointment import Appointment
from pisa.encrypted_blob import EncryptedBlob


# Not much to test here, adding it for completeness

@fixture
def appointment_data():
    locator = urandom(32).hex()
    start_time = 100
    end_time = 120
    dispute_delta = 20
    encrypted_blob_data = urandom(100).hex()
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

    assert (locator == appointment.locator and start_time == appointment.start_time and end_time == appointment.end_time
            and EncryptedBlob(encrypted_blob_data) == appointment.encrypted_blob and cipher == appointment.cipher
            and dispute_delta == appointment.dispute_delta and hash_function == appointment.hash_function)


def test_to_json(appointment_data):
    locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function = appointment_data
    appointment = Appointment(locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function)

    json_appointment = appointment.to_json()

    assert (locator == json_appointment.get("locator") and start_time == json_appointment.get("start_time")
            and end_time == json_appointment.get("end_time") and dispute_delta == json_appointment.get("dispute_delta")
            and cipher == json_appointment.get("cipher") and hash_function == json_appointment.get("hash_function")
            and encrypted_blob_data == json_appointment.get("encrypted_blob"))