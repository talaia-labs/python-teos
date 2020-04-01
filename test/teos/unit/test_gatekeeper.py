import pytest

from teos.gatekeeper import IdentificationFailure, NotEnoughSlots

from common.cryptographer import Cryptographer

from test.teos.unit.conftest import get_random_value_hex, generate_keypair, get_config


config = get_config()


def test_init(gatekeeper):
    assert isinstance(gatekeeper.default_slots, int) and gatekeeper.default_slots == config.get("DEFAULT_SLOTS")
    assert isinstance(gatekeeper.registered_users, dict) and len(gatekeeper.registered_users) == 0


def test_add_update_user(gatekeeper):
    # add_update_user adds DEFAULT_SLOTS to a given user as long as the identifier is {02, 03}| 32-byte hex str
    user_pk = "02" + get_random_value_hex(32)

    for _ in range(10):
        current_slots = gatekeeper.registered_users.get(user_pk)
        current_slots = current_slots.get("available_slots") if current_slots is not None else 0

        gatekeeper.add_update_user(user_pk)

        assert gatekeeper.registered_users.get(user_pk).get("available_slots") == current_slots + config.get(
            "DEFAULT_SLOTS"
        )

    # The same can be checked for multiple users
    for _ in range(10):
        # The user identifier is changed every call
        user_pk = "03" + get_random_value_hex(32)

        gatekeeper.add_update_user(user_pk)
        assert gatekeeper.registered_users.get(user_pk).get("available_slots") == config.get("DEFAULT_SLOTS")


def test_add_update_user_wrong_pk(gatekeeper):
    # Passing a wrong pk defaults to the errors in check_user_pk. We can try with one.
    wrong_pk = get_random_value_hex(32)

    with pytest.raises(ValueError):
        gatekeeper.add_update_user(wrong_pk)


def test_add_update_user_wrong_pk_prefix(gatekeeper):
    # Prefixes must be 02 or 03, anything else should fail
    wrong_pk = "04" + get_random_value_hex(32)

    with pytest.raises(ValueError):
        gatekeeper.add_update_user(wrong_pk)


def test_identify_user(gatekeeper):
    # Identify user should return a user_pk for registered users. It raises
    # IdentificationFailure for invalid parameters or non-registered users.

    # Let's first register a user
    sk, pk = generate_keypair()
    compressed_pk = Cryptographer.get_compressed_pk(pk)
    gatekeeper.add_update_user(compressed_pk)

    message = "Hey, it's me"
    signature = Cryptographer.sign(message.encode(), sk)

    assert gatekeeper.identify_user(message.encode(), signature) == compressed_pk


def test_identify_user_non_registered(gatekeeper):
    # Non-registered user won't be identified
    sk, pk = generate_keypair()

    message = "Hey, it's me"
    signature = Cryptographer.sign(message.encode(), sk)

    with pytest.raises(IdentificationFailure):
        gatekeeper.identify_user(message.encode(), signature)


def test_identify_user_invalid_signature(gatekeeper):
    # If the signature does not match the message given a public key, the user won't be identified
    message = "Hey, it's me"
    signature = get_random_value_hex(72)

    with pytest.raises(IdentificationFailure):
        gatekeeper.identify_user(message.encode(), signature)


def test_identify_user_wrong(gatekeeper):
    # Wrong parameters shouldn't verify either
    sk, pk = generate_keypair()

    message = "Hey, it's me"
    signature = Cryptographer.sign(message.encode(), sk)

    # Non-byte message and str sig
    with pytest.raises(IdentificationFailure):
        gatekeeper.identify_user(message, signature)

    # byte message and non-str sig
    with pytest.raises(IdentificationFailure):
        gatekeeper.identify_user(message.encode(), signature.encode())

    # non-byte message and non-str sig
    with pytest.raises(IdentificationFailure):
        gatekeeper.identify_user(message, signature.encode())


def test_fill_slots(gatekeeper):
    # Free slots will decrease the slot count of a user as long as he has enough slots, otherwise raise NotEnoughSlots
    user_pk = "02" + get_random_value_hex(32)
    gatekeeper.add_update_user(user_pk)

    gatekeeper.fill_slots(user_pk, config.get("DEFAULT_SLOTS") - 1)
    assert gatekeeper.registered_users.get(user_pk).get("available_slots") == 1

    with pytest.raises(NotEnoughSlots):
        gatekeeper.fill_slots(user_pk, 2)

    # NotEnoughSlots is also raised if the user does not exist
    with pytest.raises(NotEnoughSlots):
        gatekeeper.fill_slots(get_random_value_hex(33), 2)


def test_free_slots(gatekeeper):
    # Free slots simply adds slots to the user as long as it exists.
    user_pk = "03" + get_random_value_hex(32)
    gatekeeper.add_update_user(user_pk)
    gatekeeper.free_slots(user_pk, 42)

    assert gatekeeper.registered_users.get(user_pk).get("available_slots") == config.get("DEFAULT_SLOTS") + 42

    # Just making sure it does not crash for non-registered user
    assert gatekeeper.free_slots(get_random_value_hex(33), 10) is None
