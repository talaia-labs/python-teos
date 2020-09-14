import struct
import pytest

from common.appointment import Appointment


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

    assert locator.hex() == appointment.locator
    assert encrypted_blob.hex() == appointment.encrypted_blob
    assert int.from_bytes(to_self_delay, "big") == appointment.to_self_delay
