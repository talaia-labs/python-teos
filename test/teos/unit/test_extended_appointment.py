import pytest

from common.constants import LOCATOR_LEN_BYTES
from common.cryptographer import Cryptographer
from teos.extended_appointment import ExtendedAppointment

from test.teos.unit.conftest import get_random_value_hex, generate_keypair


# Parent methods are not tested.
@pytest.fixture
def appointment_data():
    sk, pk = generate_keypair()
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    encrypted_blob_data = get_random_value_hex(100)
    to_self_delay = 20
    user_id = Cryptographer.get_compressed_pk(pk)
    user_signature = Cryptographer.sign(encrypted_blob_data.encode("utf-8"), sk)
    start_block = 300

    return {
        "locator": locator,
        "to_self_delay": to_self_delay,
        "encrypted_blob": encrypted_blob_data,
        "user_id": user_id,
        "user_signature": user_signature,
        "start_block": start_block,
    }


def test_init_appointment(appointment_data):
    # The appointment has no checks whatsoever, since the inspector is the one taking care or that, and the only one
    # creating appointments.
    appointment = ExtendedAppointment(
        appointment_data["locator"],
        appointment_data["encrypted_blob"],
        appointment_data["to_self_delay"],
        appointment_data["user_id"],
        appointment_data["user_signature"],
        appointment_data["start_block"],
    )

    assert (
        appointment_data["locator"] == appointment.locator
        and appointment_data["to_self_delay"] == appointment.to_self_delay
        and appointment_data["encrypted_blob"] == appointment.encrypted_blob
        and appointment_data["user_id"] == appointment.user_id
        and appointment_data["user_signature"] == appointment.user_signature
        and appointment_data["start_block"] == appointment.start_block
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
