import pytest

from teos.extended_appointment import ExtendedAppointment


@pytest.fixture
def ext_appointment_data(generate_dummy_appointment):
    return generate_dummy_appointment().to_dict()


# Parent methods are not tested.


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
