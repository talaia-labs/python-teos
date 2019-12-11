import json
from pytest import fixture

from pisa import c_logger
from pisa.appointment import Appointment
from pisa.encrypted_blob import EncryptedBlob

from test.unit.conftest import get_random_value_hex

from common.constants import LOCATOR_LEN_BYTES


c_logger.disabled = True


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
    # DISCUSS: whether this makes sense by design or checks should be ported from the inspector to the appointment
    #          35-appointment-checks
    appointment = Appointment(
        appointment_data["locator"],
        appointment_data["start_time"],
        appointment_data["end_time"],
        appointment_data["to_self_delay"],
        appointment_data["encrypted_blob"],
    )

    assert (
        appointment_data["locator"] == appointment.locator
        and appointment_data["start_time"] == appointment.start_time
        and appointment_data["end_time"] == appointment.end_time
        and appointment_data["to_self_delay"] == appointment.to_self_delay
        and EncryptedBlob(appointment_data["encrypted_blob"]) == appointment.encrypted_blob
    )


def test_to_dict(appointment_data):
    appointment = Appointment(
        appointment_data["locator"],
        appointment_data["start_time"],
        appointment_data["end_time"],
        appointment_data["to_self_delay"],
        appointment_data["encrypted_blob"],
    )

    dict_appointment = appointment.to_dict()

    assert (
        appointment_data["locator"] == dict_appointment["locator"]
        and appointment_data["start_time"] == dict_appointment["start_time"]
        and appointment_data["end_time"] == dict_appointment["end_time"]
        and appointment_data["to_self_delay"] == dict_appointment["to_self_delay"]
        and EncryptedBlob(appointment_data["encrypted_blob"]) == EncryptedBlob(dict_appointment["encrypted_blob"])
    )


def test_to_json(appointment_data):
    appointment = Appointment(
        appointment_data["locator"],
        appointment_data["start_time"],
        appointment_data["end_time"],
        appointment_data["to_self_delay"],
        appointment_data["encrypted_blob"],
    )

    dict_appointment = json.loads(appointment.to_json())

    assert (
        appointment_data["locator"] == dict_appointment["locator"]
        and appointment_data["start_time"] == dict_appointment["start_time"]
        and appointment_data["end_time"] == dict_appointment["end_time"]
        and appointment_data["to_self_delay"] == dict_appointment["to_self_delay"]
        and EncryptedBlob(appointment_data["encrypted_blob"]) == EncryptedBlob(dict_appointment["encrypted_blob"])
    )


def test_from_dict(appointment_data):
    # The appointment should be build if we don't miss any field
    appointment = Appointment.from_dict(appointment_data)
    assert isinstance(appointment, Appointment)

    # Otherwise it should fail
    for key in appointment_data.keys():
        prev_val = appointment_data[key]
        appointment_data[key] = None

        try:
            Appointment.from_dict(appointment_data)
            assert False

        except ValueError:
            appointment_data[key] = prev_val
            assert True
