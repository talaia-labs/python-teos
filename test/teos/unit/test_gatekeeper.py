import pytest

from teos.users_dbm import UsersDBM
from teos.block_processor import BlockProcessor
from teos.gatekeeper import AuthenticationFailure, NotEnoughSlots, UserInfo

from common.cryptographer import Cryptographer
from common.exceptions import InvalidParameter
from common.constants import ENCRYPTED_BLOB_MAX_SIZE_HEX

from test.teos.conftest import config
from test.teos.unit.conftest import get_random_value_hex, generate_keypair


# FIXME: 194 this whole test file could work with a gatekeeper build using a dummy block_processor
def test_init(gatekeeper):
    assert isinstance(gatekeeper.subscription_slots, int) and gatekeeper.subscription_slots == config.get(
        "SUBSCRIPTION_SLOTS"
    )
    assert isinstance(gatekeeper.subscription_duration, int) and gatekeeper.subscription_duration == config.get(
        "SUBSCRIPTION_DURATION"
    )
    assert isinstance(gatekeeper.expiry_delta, int) and gatekeeper.expiry_delta == config.get("EXPIRY_DELTA")
    assert isinstance(gatekeeper.block_processor, BlockProcessor)
    assert isinstance(gatekeeper.user_db, UsersDBM)
    assert isinstance(gatekeeper.registered_users, dict) and len(gatekeeper.registered_users) == 0


def test_add_update_user(gatekeeper):
    # add_update_user adds SUBSCRIPTION_SLOTS to a given user as long as the identifier is {02, 03}| 32-byte hex str
    # it also add SUBSCRIPTION_DURATION + current_block_height to the user
    user_id = "02" + get_random_value_hex(32)

    for _ in range(10):
        user = gatekeeper.registered_users.get(user_id)
        current_slots = user.available_slots if user is not None else 0

        gatekeeper.add_update_user(user_id)

        assert gatekeeper.registered_users.get(user_id).available_slots == current_slots + config.get(
            "SUBSCRIPTION_SLOTS"
        )
        assert gatekeeper.registered_users[
            user_id
        ].subscription_expiry == gatekeeper.block_processor.get_block_count() + config.get("SUBSCRIPTION_DURATION")

    # The same can be checked for multiple users
    for _ in range(10):
        # The user identifier is changed every call
        user_id = "03" + get_random_value_hex(32)

        gatekeeper.add_update_user(user_id)
        assert gatekeeper.registered_users.get(user_id).available_slots == config.get("SUBSCRIPTION_SLOTS")
        assert gatekeeper.registered_users[
            user_id
        ].subscription_expiry == gatekeeper.block_processor.get_block_count() + config.get("SUBSCRIPTION_DURATION")


def test_add_update_user_wrong_id(gatekeeper):
    # Passing a wrong pk defaults to the errors in check_user_pk. We can try with one.
    wrong_id = get_random_value_hex(32)

    with pytest.raises(InvalidParameter):
        gatekeeper.add_update_user(wrong_id)


def test_add_update_user_wrong_id_prefix(gatekeeper):
    # Prefixes must be 02 or 03, anything else should fail
    wrong_id = "04" + get_random_value_hex(32)

    with pytest.raises(InvalidParameter):
        gatekeeper.add_update_user(wrong_id)


def test_add_update_user_overflow(gatekeeper):
    # Make sure that the available_slots in the user subscription cannot overflow

    # First lets add the user
    user_id = "03" + get_random_value_hex(32)
    gatekeeper.add_update_user(user_id)

    # Now let's set the available_slots to the max (2**32-1)
    gatekeeper.registered_users[user_id].available_slots = pow(2, 32) - 1

    # Check that it cannot accept anymore
    with pytest.raises(InvalidParameter, match="Maximum slots reached"):
        gatekeeper.add_update_user(user_id)

    # Same if the default amount of slots added per query cannot be added to the current slot count
    gatekeeper.registered_users[user_id].available_slots = pow(2, 32) - gatekeeper.subscription_slots

    with pytest.raises(InvalidParameter, match="Maximum slots reached"):
        gatekeeper.add_update_user(user_id)

    # It should work as long as we don't go over the top
    gatekeeper.registered_users[user_id].available_slots = pow(2, 32) - gatekeeper.subscription_slots - 1
    gatekeeper.add_update_user(user_id)


def test_identify_user(gatekeeper):
    # Identify user should return a user_pk for registered users. It raises
    # IdentificationFailure for invalid parameters or non-registered users.

    # Let's first register a user
    sk, pk = generate_keypair()
    user_id = Cryptographer.get_compressed_pk(pk)
    gatekeeper.add_update_user(user_id)

    message = "Hey, it's me"
    signature = Cryptographer.sign(message.encode(), sk)

    assert gatekeeper.authenticate_user(message.encode(), signature) == user_id


def test_identify_user_non_registered(gatekeeper):
    # Non-registered user won't be identified
    sk, pk = generate_keypair()

    message = "Hey, it's me"
    signature = Cryptographer.sign(message.encode(), sk)

    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message.encode(), signature)


def test_identify_user_invalid_signature(gatekeeper):
    # If the signature does not match the message given a public key, the user won't be identified
    message = "Hey, it's me"
    signature = get_random_value_hex(72)

    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message.encode(), signature)


def test_identify_user_wrong(gatekeeper):
    # Wrong parameters shouldn't verify either
    sk, pk = generate_keypair()

    message = "Hey, it's me"
    signature = Cryptographer.sign(message.encode(), sk)

    # Non-byte message and str sig
    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message, signature)

    # byte message and non-str sig
    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message.encode(), signature.encode())

    # non-byte message and non-str sig
    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message, signature.encode())


# FIXME: 194 will do with dummy appointment
def test_add_update_appointment(gatekeeper, generate_dummy_appointment):
    # add_update_appointment should decrease the slot count if a new appointment is added
    # let's add a new user
    sk, pk = generate_keypair()
    user_id = Cryptographer.get_compressed_pk(pk)
    gatekeeper.add_update_user(user_id)

    # And now update add a new appointment
    appointment, _ = generate_dummy_appointment()
    appointment_uuid = get_random_value_hex(16)
    remaining_slots = gatekeeper.add_update_appointment(user_id, appointment_uuid, appointment)

    # This is a standard size appointment, so it should have reduced the slots by one
    assert appointment_uuid in gatekeeper.registered_users[user_id].appointments
    assert remaining_slots == config.get("SUBSCRIPTION_SLOTS") - 1

    # Updates can leave the count as is, decrease it, or increase it, depending on the appointment size (modulo
    # ENCRYPTED_BLOB_MAX_SIZE_HEX)

    # Appointments of the same size leave it as is
    appointment_same_size, _ = generate_dummy_appointment()
    remaining_slots = gatekeeper.add_update_appointment(user_id, appointment_uuid, appointment)
    assert appointment_uuid in gatekeeper.registered_users[user_id].appointments
    assert remaining_slots == config.get("SUBSCRIPTION_SLOTS") - 1

    # Bigger appointments decrease it
    appointment_x2_size = appointment_same_size
    appointment_x2_size.encrypted_blob = "A" * (ENCRYPTED_BLOB_MAX_SIZE_HEX + 1)
    remaining_slots = gatekeeper.add_update_appointment(user_id, appointment_uuid, appointment_x2_size)
    assert appointment_uuid in gatekeeper.registered_users[user_id].appointments
    assert remaining_slots == config.get("SUBSCRIPTION_SLOTS") - 2

    # Smaller appointments increase it
    remaining_slots = gatekeeper.add_update_appointment(user_id, appointment_uuid, appointment)
    assert remaining_slots == config.get("SUBSCRIPTION_SLOTS") - 1

    # If the appointment needs more slots than there's free, it should fail
    gatekeeper.registered_users[user_id].available_slots = 1
    appointment_uuid = get_random_value_hex(16)
    with pytest.raises(NotEnoughSlots):
        gatekeeper.add_update_appointment(user_id, appointment_uuid, appointment_x2_size)


def test_get_expired_appointments(gatekeeper):
    # get_expired_appointments returns a list of appointment uuids expiring at a given block

    appointment = {}
    # Let's simulate adding some users with dummy expiry times
    gatekeeper.registered_users = {}
    for i in reversed(range(100)):
        uuid = get_random_value_hex(16)
        user_appointments = [get_random_value_hex(16)]
        # Add a single appointment to the user
        gatekeeper.registered_users[uuid] = UserInfo(100, i, user_appointments)
        appointment[i] = user_appointments

    # Now let's check that reversed
    for i in range(100):
        assert gatekeeper.get_expired_appointments(i + gatekeeper.expiry_delta) == appointment[i]
