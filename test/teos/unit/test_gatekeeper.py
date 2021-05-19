import time
import pytest
from copy import deepcopy

from teos.users_dbm import UsersDBM
from teos.gatekeeper import Gatekeeper
from teos.chain_monitor import ChainMonitor
from teos.block_processor import BlockProcessor
from teos.constants import OUTDATED_USERS_CACHE_SIZE_BLOCKS
from teos.gatekeeper import AuthenticationFailure, NotEnoughSlots, UserInfo

from common.cryptographer import Cryptographer
from common.exceptions import InvalidParameter
from common.constants import ENCRYPTED_BLOB_MAX_SIZE_HEX

from test.teos.unit.test_block_processor import block_processor_wrong_connection  # noqa: F401
from test.teos.conftest import config, generate_blocks, generate_blocks_with_delay
from test.teos.unit.conftest import (
    get_random_value_hex,
    generate_keypair,
    bitcoind_connect_params,
    wrong_bitcoind_connect_params,
    run_test_command_bitcoind_crash,
    run_test_blocking_command_bitcoind_crash,
)


@pytest.fixture(scope="module")
def gatekeeper_wrong_connection(user_db_manager, block_processor_wrong_connection):  # noqa: F811
    return Gatekeeper(
        user_db_manager,
        block_processor_wrong_connection,
        config.get("SUBSCRIPTION_SLOTS"),
        config.get("SUBSCRIPTION_DURATION"),
        config.get("EXPIRY_DELTA"),
    )


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


def test_manage_subscription_expiry(gatekeeper):
    # The subscription are expired at expiry but data is deleted once outdated (expiry_delta blocks after)
    current_height = gatekeeper.block_processor.get_block_count()
    expiring_users = {
        get_random_value_hex(32): UserInfo(available_slots=10, subscription_expiry=current_height + 1)
        for _ in range(10)
    }
    gatekeeper.registered_users.update(expiring_users)

    # We will need a ChainMonitor instance for this so data can be feed to us
    bitcoind_feed_params = {k: v for k, v in config.items() if k.startswith("BTC_FEED")}
    chain_monitor = ChainMonitor([gatekeeper.block_queue], gatekeeper.block_processor, bitcoind_feed_params)
    chain_monitor.monitor_chain()
    chain_monitor.activate()

    # Users expire after this block. Check that they are currently not expired
    for user_id in expiring_users.keys():
        has_subscription_expired, _ = gatekeeper.has_subscription_expired(user_id)
        assert not has_subscription_expired

    # Generate a block and users must have expired
    generate_blocks_with_delay(1)
    for user_id in expiring_users.keys():
        has_subscription_expired, _ = gatekeeper.has_subscription_expired(user_id)
        assert has_subscription_expired

    # Users will remain in the registered_users dictionary until expiry_delta blocks later.
    generate_blocks_with_delay(gatekeeper.expiry_delta - 1)
    # Users will be deleted in the next block
    assert set(expiring_users).issubset(gatekeeper.registered_users)

    generate_blocks_with_delay(1)
    # Data has just been deleted but should still be present on the cache
    block_height_deletion = gatekeeper.block_processor.get_block_count()
    assert not set(expiring_users).issubset(gatekeeper.registered_users)
    for user_id, _ in expiring_users.items():
        assert not gatekeeper.user_db.load_user(user_id)
    assert gatekeeper.outdated_users_cache[block_height_deletion].keys() == expiring_users.keys()

    # After OUTDATED_USERS_CACHE_SIZE_BLOCKS they data should not be there anymore (check one before and the one)
    generate_blocks_with_delay(OUTDATED_USERS_CACHE_SIZE_BLOCKS - 1)
    assert block_height_deletion in gatekeeper.outdated_users_cache
    generate_blocks_with_delay(1)
    assert block_height_deletion not in gatekeeper.outdated_users_cache


def test_manage_subscription_expiry_bitcoind_crash(gatekeeper):
    # Test that the data is not deleted until bitcoind comes back online
    current_height = gatekeeper.block_processor.get_block_count()
    user_id = get_random_value_hex(32)
    expiring_users = {user_id: UserInfo(available_slots=10, subscription_expiry=current_height + 1)}
    gatekeeper.registered_users.update(expiring_users)

    # Since the gatekeeper is not currently hooked to any ChainMonitor, it won't be notified.
    block_id = generate_blocks(1)[0]

    # Now we can set wrong connection params and feed the block to mock a crash with bitcoind
    gatekeeper.block_processor.btc_connect_params = wrong_bitcoind_connect_params
    gatekeeper.block_queue.put(block_id)
    time.sleep(1)

    # The gatekeeper's subscription manager thread should be blocked now.  The thread cannot check if the subscription
    # has expired, and the query is blocking
    assert not gatekeeper.block_processor.bitcoind_reachable.is_set()
    with pytest.raises(ConnectionRefusedError):
        gatekeeper.has_subscription_expired(user_id)

    # Setting te event should unblock the thread and expire the subscription
    gatekeeper.block_processor.btc_connect_params = bitcoind_connect_params
    gatekeeper.block_processor.bitcoind_reachable.set()
    time.sleep(1)

    has_subscription_expired, _ = gatekeeper.has_subscription_expired(user_id)
    assert has_subscription_expired


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
    signature = Cryptographer.sign(message.encode("utf-8"), sk)

    assert gatekeeper.authenticate_user(message.encode("utf-8"), signature) == user_id


def test_identify_user_non_registered(gatekeeper):
    # Non-registered user won't be identified
    sk, pk = generate_keypair()

    message = "Hey, it's me"
    signature = Cryptographer.sign(message.encode("utf-8"), sk)

    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message.encode("utf-8"), signature)


def test_identify_user_invalid_signature(gatekeeper):
    # If the signature does not match the message given a public key, the user won't be identified
    message = "Hey, it's me"
    signature = get_random_value_hex(72)

    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message.encode("utf-8"), signature)


def test_identify_user_wrong(gatekeeper):
    # Wrong parameters shouldn't verify either
    sk, pk = generate_keypair()

    message = "Hey, it's me"
    signature = Cryptographer.sign(message.encode("utf-8"), sk)

    # Non-byte message and str sig
    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message, signature)

    # byte message and non-str sig
    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message.encode("utf-8"), signature.encode("utf-8"))

    # non-byte message and non-str sig
    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message, signature.encode("utf-8"))


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


def test_has_subscription_expired(gatekeeper):
    user_info = UserInfo(available_slots=1, subscription_expiry=gatekeeper.block_processor.get_block_count() + 1)
    user_id = get_random_value_hex(32)
    gatekeeper.registered_users[user_id] = user_info

    # Check that the subscription is still live
    has_subscription_expired, expiry = gatekeeper.has_subscription_expired(user_id)
    assert not has_subscription_expired

    # Generating 1 additional block will expire the subscription
    generate_blocks(1)
    has_subscription_expired, expiry = gatekeeper.has_subscription_expired(user_id)
    assert has_subscription_expired

    # Check it remains expired afterwards
    generate_blocks(1)
    has_subscription_expired, expiry = gatekeeper.has_subscription_expired(user_id)
    assert has_subscription_expired


def test_has_subscription_expired_not_registered(gatekeeper):
    # If the users is unknown by the Gatekeeper, the method will fail
    with pytest.raises(AuthenticationFailure):
        gatekeeper.has_subscription_expired(get_random_value_hex(32))


def test_get_outdated_users(gatekeeper):
    # Gets a list of users whose subscription gets outdated at a given height
    current_height = gatekeeper.block_processor.get_block_count()
    uuids = [get_random_value_hex(32) for _ in range(20)]
    outdated_users_next = {
        get_random_value_hex(32): UserInfo(
            available_slots=10,
            subscription_expiry=current_height - gatekeeper.expiry_delta + 1,
            appointments={uuids[i]: 1},  # uuid:1 slot
        )
        for i in range(10)
    }

    outdated_users_next_next = {
        get_random_value_hex(32): UserInfo(
            available_slots=10,
            subscription_expiry=current_height - gatekeeper.expiry_delta + 2,
            appointments={uuids[i + 10]: 1},  # uuid:1 slot
        )
        for i in range(10)
    }

    # Add users to the Gatekeeper
    gatekeeper.registered_users.update(outdated_users_next)
    gatekeeper.registered_users.update(outdated_users_next_next)

    # Check that outdated_users_cache are outdated at the current height
    outdated_users = gatekeeper.get_outdated_users(current_height + 1).keys()
    outdated_appointment_uuids = [
        uuid
        for user_appointments in gatekeeper.get_outdated_users(current_height + 1).values()
        for uuid in user_appointments
    ]
    assert outdated_users == outdated_users_next.keys() and outdated_appointment_uuids == uuids[:10]

    outdated_users = gatekeeper.get_outdated_users(current_height + 2).keys()
    outdated_appointment_uuids = [
        uuid
        for user_appointments in gatekeeper.get_outdated_users(current_height + 2).values()
        for uuid in user_appointments
    ]
    assert outdated_users == outdated_users_next_next.keys() and outdated_appointment_uuids == uuids[10:]


def test_get_outdated_user_ids(gatekeeper):
    # get_outdated_user_ids returns a list of user ids being outdated a a given height.
    uuids = []
    # Let's simulate adding some users with dummy expiry times
    gatekeeper.registered_users = {}
    for i in range(100):
        # Add more than one user expiring at the same time to check it works for multiple users
        iter_uuids = []
        for _ in range(2):
            uuid = get_random_value_hex(16)
            user_appointments = {get_random_value_hex(16): 1}
            # Add a single appointment to the user
            gatekeeper.registered_users[uuid] = UserInfo(100, i, user_appointments)
            iter_uuids.append(uuid)
        uuids.append(iter_uuids)

    # Now let's check that the appointments are outdated at the proper time
    for i in range(100):
        assert gatekeeper.get_outdated_user_ids(i + gatekeeper.expiry_delta) == uuids[i]


def test_get_outdated_user_ids_empty(gatekeeper):
    # Test how an empty list is returned if no users are being outdated
    empty = gatekeeper.get_outdated_user_ids(gatekeeper.block_processor.get_block_count() + 1000)
    assert isinstance(empty, list) and len(empty) == 0


def test_get_outdated_appointments(gatekeeper):
    # get_outdated_appointments returns a list of appointment uuids being outdated a a given height

    appointment = {}
    # Let's simulate adding some users with dummy expiry times
    gatekeeper.registered_users = {}
    for i in range(100):
        # Add more than one user expiring at the same time to check it works for multiple users
        for _ in range(2):
            uuid = get_random_value_hex(16)
            user_appointments = {get_random_value_hex(16): 1 for _ in range(10)}
            # Add a single appointment to the user
            gatekeeper.registered_users[uuid] = UserInfo(100, i, user_appointments)

            if i in appointment:
                appointment[i].update(user_appointments)
            else:
                appointment[i] = deepcopy(user_appointments)

    # Now let's check that the appointments are outdated a the proper time
    for i in range(100):
        assert gatekeeper.get_outdated_appointments(i + gatekeeper.expiry_delta) == list(appointment[i].keys())


def test_get_outdated_appointments_empty(gatekeeper):
    # Test how an empty list is returned if no appointments are being outdated
    empty = gatekeeper.get_outdated_appointments(gatekeeper.block_processor.get_block_count() + 1000)
    assert isinstance(empty, list) and len(empty) == 0


def test_update_outdated_users_cache(gatekeeper):
    # update_outdated_users_cache is used to add new entries to the cache and prune old ones if it grows beyond the
    # limit. In normal conditions (no reorg) the method is called once per block height, meaning that the data won't be
    # in the cache when called and it will be afterwards
    current_block_height = gatekeeper.block_processor.get_block_count()
    appointments = {get_random_value_hex(32): 1 for _ in range(10)}
    user_info = UserInfo(available_slots=1, subscription_expiry=current_block_height + 42, appointments=appointments)
    user_id = get_random_value_hex(32)
    gatekeeper.registered_users[user_id] = user_info

    # Check that the entry is not in the cache
    target_height = current_block_height + gatekeeper.expiry_delta + 42
    assert target_height not in gatekeeper.outdated_users_cache

    # Update the cache and check
    gatekeeper.update_outdated_users_cache(target_height)
    cache_entry = gatekeeper.outdated_users_cache.get(target_height)
    # Values is not meant to be used straightaway for checking, but we can flatten it to check it matches
    flattened_appointments = [uuid for user_appointments in cache_entry.values() for uuid in user_appointments]
    assert list(cache_entry.keys()) == [user_id] and flattened_appointments == list(appointments.keys())


def test_update_outdated_users_cache_remove_data(gatekeeper):
    # Tests how the oldest piece of data is removed after OUTDATED_USERS_CACHE_SIZE_BLOCKS
    current_block_height = gatekeeper.block_processor.get_block_count()

    # Add users that are expiring from the current block to OUTDATED_USERS_CACHE_SIZE_BLOCKS -1 and fill the cache with
    # them
    data = {}
    for i in range(OUTDATED_USERS_CACHE_SIZE_BLOCKS):
        appointments = {get_random_value_hex(32): 1 for _ in range(10)}
        user_info = UserInfo(available_slots=1, subscription_expiry=current_block_height + i, appointments=appointments)
        user_id = get_random_value_hex(32)
        gatekeeper.registered_users[user_id] = user_info

        target_block = current_block_height + gatekeeper.expiry_delta + i
        gatekeeper.update_outdated_users_cache(target_block)
        # Create a local version of the expected data to compare {block_id: {user_id: [appointment_uuids]}, ...}
        data[target_block] = {user_id: list(appointments.keys())}

    # Check that the cache is full and that each position matches
    assert len(gatekeeper.outdated_users_cache) == OUTDATED_USERS_CACHE_SIZE_BLOCKS
    assert gatekeeper.outdated_users_cache == data

    # Add more blocks and check what data gets kicked (data has an offset of OUTDATED_USERS_CACHE_SIZE_BLOCKS, so we can
    # check if the previous key is there easily)
    for i in range(OUTDATED_USERS_CACHE_SIZE_BLOCKS):
        target_block = current_block_height + gatekeeper.expiry_delta + OUTDATED_USERS_CACHE_SIZE_BLOCKS + i
        assert target_block - OUTDATED_USERS_CACHE_SIZE_BLOCKS in gatekeeper.outdated_users_cache
        gatekeeper.update_outdated_users_cache(target_block)
        assert target_block - OUTDATED_USERS_CACHE_SIZE_BLOCKS not in gatekeeper.outdated_users_cache


# TESTS WITH BITCOIND UNREACHABLE


def test_add_update_user_bitcoind_crash(gatekeeper, gatekeeper_wrong_connection):
    user_id = "02" + get_random_value_hex(32)
    run_test_command_bitcoind_crash(lambda: gatekeeper_wrong_connection.add_update_user(user_id))
    run_test_blocking_command_bitcoind_crash(
        gatekeeper.block_processor.bitcoind_reachable, lambda: gatekeeper.add_update_user(user_id)
    )


def test_has_subscription_expired_bitcoind_crash(gatekeeper, gatekeeper_wrong_connection):
    user_id = "02" + get_random_value_hex(32)
    # Add the user to both the gatekeeper's so there's data to check against
    gatekeeper_wrong_connection.registered_users.update({user_id: UserInfo(available_slots=10, subscription_expiry=1)})
    gatekeeper.registered_users.update({user_id: UserInfo(available_slots=10, subscription_expiry=1)})

    run_test_command_bitcoind_crash(lambda: gatekeeper_wrong_connection.has_subscription_expired(user_id))
    run_test_blocking_command_bitcoind_crash(
        gatekeeper.block_processor.bitcoind_reachable, lambda: gatekeeper.has_subscription_expired(user_id)
    )
