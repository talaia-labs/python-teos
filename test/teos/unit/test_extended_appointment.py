import pytest
from pytest import fixture

from common.constants import LOCATOR_LEN_BYTES
from teos.extended_appointment import ExtendedAppointment

from test.common.unit.conftest import get_random_value_hex


# Parent methods are not tested.
@fixture
def appointment_data():
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    to_self_delay = 20
    user_id = get_random_value_hex(16)
    encrypted_blob_data = get_random_value_hex(100)

    return {
        "locator": locator,
        "to_self_delay": to_self_delay,
        "encrypted_blob": encrypted_blob_data,
        "user_id": user_id,
    }


def test_init_appointment(appointment_data):
    # The appointment has no checks whatsoever, since the inspector is the one taking care or that, and the only one
    # creating appointments.
    appointment = ExtendedAppointment(
        appointment_data["locator"],
        appointment_data["to_self_delay"],
        appointment_data["encrypted_blob"],
        appointment_data["user_id"],
    )

    assert (
        appointment_data["locator"] == appointment.locator
        and appointment_data["to_self_delay"] == appointment.to_self_delay
        and appointment_data["encrypted_blob"] == appointment.encrypted_blob
        and appointment_data["user_id"] == appointment.user_id
    )


def test_get_summary(appointment_data):
    assert ExtendedAppointment.from_dict(appointment_data).get_summary() == {
        "locator": appointment_data["locator"],
        "user_id": appointment_data["user_id"],
    }


def test_from_dict(appointment_data):
    # The appointment should be build if we don't miss any field
    appointment = ExtendedAppointment.from_dict(appointment_data)
    assert isinstance(appointment, ExtendedAppointment)

    # Otherwise it should fail
    for key in appointment_data.keys():
        prev_val = appointment_data[key]
        appointment_data[key] = None

        with pytest.raises(ValueError, match="Wrong appointment data"):
            ExtendedAppointment.from_dict(appointment_data)
            appointment_data[key] = prev_val
