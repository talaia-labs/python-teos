import pytest

from teos.gatekeeper import AuthenticationFailure, NotEnoughSlots

from common.cryptographer import Cryptographer
from common.exceptions import InvalidParameter

from test.teos.unit.conftest import get_random_value_hex, generate_keypair, get_config


config = get_config()


def test_init(gatekeeper, run_bitcoind):
    assert isinstance(gatekeeper.default_slots, int) and gatekeeper.default_slots == config.get("DEFAULT_SLOTS")
    assert isinstance(gatekeeper.registered_users, dict) and len(gatekeeper.registered_users) == 0


def test_add_update_user(gatekeeper):
    # add_update_user adds DEFAULT_SLOTS to a given user as long as the identifier is {02, 03}| 32-byte hex str
    user_pk = "02" + get_random_value_hex(32)

    for _ in range(10):
        user = gatekeeper.registered_users.get(user_pk)
        current_slots = user.available_slots if user is not None else 0

        gatekeeper.add_update_user(user_pk)

        assert gatekeeper.registered_users.get(user_pk).available_slots == current_slots + config.get("DEFAULT_SLOTS")

    # The same can be checked for multiple users
    for _ in range(10):
        # The user identifier is changed every call
        user_pk = "03" + get_random_value_hex(32)

        gatekeeper.add_update_user(user_pk)
        assert gatekeeper.registered_users.get(user_pk).available_slots == config.get("DEFAULT_SLOTS")


def test_add_update_user_wrong_pk(gatekeeper):
    # Passing a wrong pk defaults to the errors in check_user_pk. We can try with one.
    wrong_pk = get_random_value_hex(32)

    with pytest.raises(InvalidParameter):
        gatekeeper.add_update_user(wrong_pk)


def test_add_update_user_wrong_pk_prefix(gatekeeper):
    # Prefixes must be 02 or 03, anything else should fail
    wrong_pk = "04" + get_random_value_hex(32)

    with pytest.raises(InvalidParameter):
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

    assert gatekeeper.authenticate_user(message.encode(), signature) == compressed_pk


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


# FIXME: MISSING TESTS
