import pytest

from common.constants import LOCATOR_LEN_BYTES
from common.cryptographer import Cryptographer
from teos.extended_appointment import ExtendedAppointment

from test.teos.unit.conftest import get_random_value_hex, generate_keypair


# Parent methods are not tested.
@pytest.fixture
def ext_appointment_data():
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


def test_init_ext_appointment(ext_appointment_data):
    # The appointment has no checks whatsoever, since the inspector is the one taking care or that, and the only one
    # creating appointments.
    ext_appointment = ExtendedAppointment(
        ext_appointment_data["locator"],
        ext_appointment_data["encrypted_blob"],
        ext_appointment_data["to_self_delay"],
        ext_appointment_data["user_id"],
        ext_appointment_data["user_signature"],
        ext_appointment_data["start_block"],
    )

    assert (
        ext_appointment_data["locator"] == ext_appointment.locator
        and ext_appointment_data["to_self_delay"] == ext_appointment.to_self_delay
        and ext_appointment_data["encrypted_blob"] == ext_appointment.encrypted_blob
        and ext_appointment_data["user_id"] == ext_appointment.user_id
        and ext_appointment_data["user_signature"] == ext_appointment.user_signature
        and ext_appointment_data["start_block"] == ext_appointment.start_block
    )


def test_get_summary(ext_appointment_data):
    assert ExtendedAppointment.from_dict(ext_appointment_data).get_summary() == {
        "locator": ext_appointment_data["locator"],
        "user_id": ext_appointment_data["user_id"],
    }


def test_from_dict(ext_appointment_data):
    # The appointment should be build if we don't miss any field
    ext_appointment = ExtendedAppointment.from_dict(ext_appointment_data)
    assert isinstance(ext_appointment, ExtendedAppointment)

    # Otherwise it should fail
    for key in ext_appointment_data.keys():
        prev_val = ext_appointment_data[key]
        ext_appointment_data[key] = None

        with pytest.raises(ValueError, match="Wrong appointment data"):
            ExtendedAppointment.from_dict(ext_appointment_data)
            ext_appointment_data[key] = prev_val
