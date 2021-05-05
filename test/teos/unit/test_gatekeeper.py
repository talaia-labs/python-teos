import time
import pytest
import itertools
from shutil import rmtree
from copy import deepcopy

from teos.users_dbm import UsersDBM
from teos.gatekeeper import Gatekeeper
from teos.constants import OUTDATED_USERS_CACHE_SIZE_BLOCKS
from teos.gatekeeper import AuthenticationFailure, NotEnoughSlots, UserInfo

from common.exceptions import InvalidParameter
from common.cryptographer import Cryptographer
from common.constants import ENCRYPTED_BLOB_MAX_SIZE_HEX

from test.teos.unit.mocks import BlockProcessor as BlockProcessor
from test.teos.conftest import config, mock_generate_blocks, generate_blocks
from test.teos.unit.test_block_processor import block_processor_wrong_connection  # noqa: F401
from test.teos.unit.conftest import (
    get_random_value_hex,
    generate_keypair,
    bitcoind_connect_params,
    wrong_bitcoind_connect_params,
    run_test_command_bitcoind_crash,
)

flatten = itertools.chain.from_iterable


@pytest.fixture(scope="module")
def user_db_manager():
    manager = UsersDBM("test_user_db")
    # Add last know block for the Responder in the db

    yield manager

    manager.db.close()
    rmtree("test_user_db")


@pytest.fixture
def gatekeeper_wrong_connection(user_db_manager, block_processor_wrong_connection):  # noqa: F811
    return Gatekeeper(
        user_db_manager,
        block_processor_wrong_connection,
        config.get("SUBSCRIPTION_SLOTS"),
        config.get("SUBSCRIPTION_DURATION"),
        config.get("EXPIRY_DELTA"),
    )


@pytest.fixture
def gatekeeper(user_db_manager, block_processor_mock):
    return Gatekeeper(
        user_db_manager,
        block_processor_mock,
        config.get("SUBSCRIPTION_SLOTS"),
        config.get("SUBSCRIPTION_DURATION"),
        config.get("EXPIRY_DELTA"),
    )


@pytest.fixture
def gatekeeper_real_bp(gatekeeper, block_processor, monkeypatch):
    monkeypatch.setattr(gatekeeper, "block_processor", block_processor)

    return gatekeeper


# USER INFO


def test_user_info_init():
    available_slots = 42
    subscription_expiry = 1234

    # UserInfo objects can be created without appointments
    user_info = UserInfo(available_slots, subscription_expiry)
    assert user_info.available_slots == available_slots
    assert user_info.subscription_expiry == subscription_expiry
    assert user_info.appointments == {}

    # But also with, in case they are being restored from the database (the actual data does not matter here)
    appointments = {get_random_value_hex(32): 1 for _ in range(10)}
    user_info = UserInfo(available_slots, subscription_expiry, appointments)
    assert user_info.available_slots == available_slots
    assert user_info.subscription_expiry == subscription_expiry
    assert user_info.appointments == appointments


def test_user_info_from_dict():
    # UserInfo objects can be created from a dictionary, this is used when loading data from the database
    available_slots = 42
    subscription_expiry = 1234
    appointments = {get_random_value_hex(32): 1 for _ in range(10)}
    data = {
        "available_slots": available_slots,
        "subscription_expiry": subscription_expiry,
        "appointments": appointments,
    }

    user_info = UserInfo.from_dict(data)
    assert user_info.available_slots == available_slots
    assert user_info.subscription_expiry == subscription_expiry
    assert user_info.appointments == appointments

    # The appointments dict does not need to be populated when building from a dictionary
    data["appointments"] = {}
    user_info = UserInfo.from_dict(data)
    assert user_info.available_slots == available_slots
    assert user_info.subscription_expiry == subscription_expiry
    assert user_info.appointments == {}


def test_user_info_from_dict_wrong_data():
    # If any of the dictionary fields is missing, building from dict will fail
    d1 = {"available_slots": "", "subscription_expiry": ""}
    d2 = {"available_slots": "", "appointments": ""}
    d3 = {"subscription_expiry": "", "appointments": ""}

    for d in [d1, d2, d3]:
        with pytest.raises(ValueError, match="Wrong appointment data, some fields are missing"):
            UserInfo.from_dict(d)


# GATEKEEPER


def test_gatekeeper_init(gatekeeper):
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


def test_manage_subscription_expiry(gatekeeper, monkeypatch):
    # A thread to manage the subscription expiry is created when the Gatekeeper is created.
    # Subscriptions are expired at expiry but data is deleted once outdated (expiry_delta blocks after)
    init_height = 0
    blocks = dict()

    # Mock the required BlockProcessor calls from the Gatekeeper
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: init_height + len(blocks))
    monkeypatch.setattr(
        gatekeeper.block_processor,
        "get_block",
        lambda x, blocking: {"height": init_height + list(blocks.keys()).index(x) + 1},
    )

    # Mock adding the expiring users to the Gatekeeper
    expiring_users = {
        get_random_value_hex(32): UserInfo(available_slots=10, subscription_expiry=init_height + 1) for _ in range(10)
    }
    gatekeeper.registered_users.update(expiring_users)

    # Users expire after the current block. Check that they are currently not expired
    for user_id in expiring_users.keys():
        has_subscription_expired, _ = gatekeeper.has_subscription_expired(user_id)
        assert not has_subscription_expired

    # Generate a block and users must have expired
    mock_generate_blocks(1, blocks, gatekeeper.block_queue)
    for user_id in expiring_users.keys():
        has_subscription_expired, _ = gatekeeper.has_subscription_expired(user_id)
        assert has_subscription_expired

    # Users will remain in registered_users until expiry_delta blocks later (check one before and the one)
    mock_generate_blocks(gatekeeper.expiry_delta - 1, blocks, gatekeeper.block_queue)
    assert expiring_users.keys() == gatekeeper.registered_users.keys()
    mock_generate_blocks(1, blocks, gatekeeper.block_queue)
    assert len(gatekeeper.registered_users) == 0

    # Data should also have been deleted from the database
    block_height_deletion = gatekeeper.block_processor.get_block_count()
    for user_id, _ in expiring_users.items():
        assert not gatekeeper.user_db.load_user(user_id)
    assert gatekeeper.outdated_users_cache[block_height_deletion].keys() == expiring_users.keys()

    # Data should be removed from the cache OUTDATED_USERS_CACHE_SIZE_BLOCKS after expiry (check one before and the one)
    mock_generate_blocks(OUTDATED_USERS_CACHE_SIZE_BLOCKS - 1, blocks, gatekeeper.block_queue)
    assert block_height_deletion in gatekeeper.outdated_users_cache
    mock_generate_blocks(1, blocks, gatekeeper.block_queue)
    assert block_height_deletion not in gatekeeper.outdated_users_cache


def test_add_update_user(gatekeeper, monkeypatch):
    # add_update_user adds SUBSCRIPTION_SLOTS to a given user as long as the identifier is {02, 03}| 32-byte hex str.
    # It also adds SUBSCRIPTION_DURATION + current_block_height to the user
    user_id = "02" + get_random_value_hex(32)
    init_height = 0

    # Mock the required BlockProcessor calls from the Gatekeeper
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: init_height)

    for i in range(10):
        gatekeeper.add_update_user(user_id)
        user = gatekeeper.registered_users.get(user_id)

        assert user.available_slots == config.get("SUBSCRIPTION_SLOTS") * (i + 1)
        assert user.subscription_expiry == init_height + config.get("SUBSCRIPTION_DURATION")

    # The same can be checked for multiple users
    for _ in range(10):
        # The user identifier is changed every call
        user_id = "03" + get_random_value_hex(32)
        gatekeeper.add_update_user(user_id)
        user = gatekeeper.registered_users.get(user_id)

        assert user.available_slots == config.get("SUBSCRIPTION_SLOTS")
        assert user.subscription_expiry == init_height + config.get("SUBSCRIPTION_DURATION")


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


def test_add_update_user_overflow(gatekeeper, monkeypatch):
    # Make sure that the available_slots in the user subscription cannot overflow

    # Mock the required BlockProcessor calls from the Gatekeeper
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: 0)

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


def test_authenticate_user(gatekeeper, monkeypatch):
    # Authenticate user should return a user_pk for registered users. It raises IdentificationFailure for invalid
    # parameters or non-registered users.

    # Mock the required BlockProcessor calls from the Gatekeeper
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: 0)

    # Let's first register a user
    sk, pk = generate_keypair()
    user_id = Cryptographer.get_compressed_pk(pk)
    # Mock the user registration
    monkeypatch.setitem(gatekeeper.registered_users, user_id, {})

    message = "Hey, it's me"
    signature = Cryptographer.sign(message.encode("utf-8"), sk)

    assert gatekeeper.authenticate_user(message.encode("utf-8"), signature) == user_id


def test_authenticate_user_non_registered(gatekeeper):
    # Non-registered user won't be authenticated
    sk, pk = generate_keypair()

    message = "Hey, it's me"
    signature = Cryptographer.sign(message.encode("utf-8"), sk)

    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message.encode("utf-8"), signature)


def test_authenticate_user_invalid_signature(gatekeeper):
    # If the signature does not match the message given a public key, the user won't be authenticated
    message = "Hey, it's me"
    signature = get_random_value_hex(72)

    with pytest.raises(AuthenticationFailure):
        gatekeeper.authenticate_user(message.encode("utf-8"), signature)


def test_authenticate_user_wrong(gatekeeper):
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


def test_add_update_appointment(gatekeeper, generate_dummy_appointment, monkeypatch):
    # add_update_appointment should decrease the slot count if a new appointment is added
    init_height = 0

    # Mock the required BlockProcessor calls from the Gatekeeper
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: init_height)

    # Mock the user registration
    user_id = "02" + get_random_value_hex(32)
    user_info = UserInfo(100, init_height + 100)
    monkeypatch.setitem(gatekeeper.registered_users, user_id, user_info)

    # And now add a new appointment
    appointment = generate_dummy_appointment()
    appointment_uuid = get_random_value_hex(16)
    remaining_slots = gatekeeper.add_update_appointment(user_id, appointment_uuid, appointment)

    # This is a standard size appointment, so it should have reduced the slots by one
    assert appointment_uuid in gatekeeper.registered_users[user_id].appointments
    assert remaining_slots == config.get("SUBSCRIPTION_SLOTS") - 1

    # Updates can leave the count as is, decrease it, or increase it, depending on the appointment size (modulo
    # ENCRYPTED_BLOB_MAX_SIZE_HEX)

    # Appointments of the same size leave it as is
    appointment_same_size = generate_dummy_appointment()
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


def test_has_subscription_expired(gatekeeper, monkeypatch):
    init_height = 0
    blocks = dict()

    # Mock the required BlockProcessor calls from the Gatekeeper
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: init_height + len(blocks))
    monkeypatch.setattr(
        gatekeeper.block_processor,
        "get_block",
        lambda x, blocking: {"height": init_height + list(blocks.keys()).index(x) + 1},
    )

    # Mock the user registration
    user_info = UserInfo(available_slots=1, subscription_expiry=init_height + 1)
    user_id = get_random_value_hex(32)
    monkeypatch.setitem(gatekeeper.registered_users, user_id, user_info)

    # Check that the subscription is still live
    has_subscription_expired, expiry = gatekeeper.has_subscription_expired(user_id)
    assert not has_subscription_expired

    # Generating 1 additional block will expire the subscription
    mock_generate_blocks(1, blocks, gatekeeper.block_queue)
    has_subscription_expired, expiry = gatekeeper.has_subscription_expired(user_id)
    assert has_subscription_expired

    # Check it remains expired afterwards
    mock_generate_blocks(1, blocks, gatekeeper.block_queue)
    has_subscription_expired, expiry = gatekeeper.has_subscription_expired(user_id)
    assert has_subscription_expired


def test_has_subscription_expired_not_registered(gatekeeper):
    # If the users is unknown by the Gatekeeper, the method will fail
    with pytest.raises(AuthenticationFailure):
        gatekeeper.has_subscription_expired(get_random_value_hex(32))


def test_get_outdated_users(gatekeeper, monkeypatch):
    init_height = 0
    blocks = []

    # Mock the required BlockProcessor calls from the Gatekeeper
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: init_height + len(blocks))

    # Gets a list of users whose subscription gets outdated at a given height
    uuids = [get_random_value_hex(32) for _ in range(20)]
    outdated_users_next = {
        get_random_value_hex(32): UserInfo(
            available_slots=10,
            subscription_expiry=init_height - gatekeeper.expiry_delta + 1,
            appointments={uuids[i]: 1},  # uuid:1 slot
        )
        for i in range(10)
    }

    outdated_users_next_next = {
        get_random_value_hex(32): UserInfo(
            available_slots=10,
            subscription_expiry=init_height - gatekeeper.expiry_delta + 2,
            appointments={uuids[i + 10]: 1},  # uuid:1 slot
        )
        for i in range(10)
    }

    # Mock adding users to the Gatekeeper
    gatekeeper.registered_users.update(outdated_users_next)
    gatekeeper.registered_users.update(outdated_users_next_next)

    # Check that outdated_users_next are outdated in the next block
    outdated_users = gatekeeper.get_outdated_users(init_height + 1).keys()
    outdated_appointment_uuids = list(flatten(gatekeeper.get_outdated_users(init_height + 1).values()))
    assert outdated_users == outdated_users_next.keys() and outdated_appointment_uuids == uuids[:10]

    # Check that outdated_users_next_next are outdated in two blocks from now
    outdated_users = gatekeeper.get_outdated_users(init_height + 2).keys()
    outdated_appointment_uuids = list(flatten(gatekeeper.get_outdated_users(init_height + 2).values()))
    assert outdated_users == outdated_users_next_next.keys() and outdated_appointment_uuids == uuids[10:]


def test_get_outdated_user_ids(gatekeeper, monkeypatch):
    # get_outdated_user_ids returns a list of user ids being outdated a a given height.
    uuids = []

    # # Let's simulate adding some users with dummy expiry times
    for expiry in range(100):
        # Add more than one user expiring at the same time to check it works for multiple users
        iter_uuids = []
        for _ in range(2):
            uuid = get_random_value_hex(16)
            # Add a single appointment to the user
            user_appointments = {get_random_value_hex(16): 1}
            # Mock adding the users to the Gatekeeper
            monkeypatch.setitem(gatekeeper.registered_users, uuid, UserInfo(100, expiry, user_appointments))
            iter_uuids.append(uuid)
        uuids.append(iter_uuids)

    # Now let's check that the appointments are outdated at the proper time
    for expiry in range(100):
        assert gatekeeper.get_outdated_user_ids(expiry + gatekeeper.expiry_delta) == uuids[expiry]


def test_get_outdated_user_ids_empty(gatekeeper, monkeypatch):
    init_height = 0
    # Mock the required BlockProcessor calls from the Gatekeeper
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: init_height)

    # Test how an empty list is returned if no users are being outdated
    empty = gatekeeper.get_outdated_user_ids(init_height + 1000)
    assert isinstance(empty, list) and len(empty) == 0


def test_get_outdated_appointments(gatekeeper, monkeypatch):
    # get_outdated_appointments returns a list of appointment uuids being outdated at a given height

    appointment = {}
    # Let's simulate adding some users with dummy expiry times
    gatekeeper.registered_users = {}
    for expiry in range(100):
        # Add more than one user expiring at the same time to check it works for multiple users
        for _ in range(2):
            uuid = get_random_value_hex(16)
            user_appointments = {get_random_value_hex(16): 1 for _ in range(10)}
            # Add a single appointment to the user
            monkeypatch.setitem(gatekeeper.registered_users, uuid, UserInfo(100, expiry, user_appointments))

            if expiry in appointment:
                appointment[expiry].update(user_appointments)
            else:
                appointment[expiry] = deepcopy(user_appointments)

    # Now let's check that the appointments are outdated a the proper time
    for expiry in range(100):
        assert gatekeeper.get_outdated_appointments(expiry + gatekeeper.expiry_delta) == list(
            appointment[expiry].keys()
        )


def test_get_outdated_appointments_empty(gatekeeper, monkeypatch):
    # Mock the required BlockProcessor calls from the Gatekeeper
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: 0)

    # Test how an empty list is returned if no appointments are being outdated
    empty = gatekeeper.get_outdated_appointments(1)
    assert isinstance(empty, list) and len(empty) == 0


def test_update_outdated_users_cache(gatekeeper, monkeypatch):
    # update_outdated_users_cache is used to add new entries to the cache and prune old ones if it grows beyond the
    # limit. In normal conditions (no reorg) the method is called once per block height, meaning that the data won't be
    # in the cache when called and it will be afterwards
    # Mock the required BlockProcessor calls from the Gatekeeper
    init_height = 0
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: init_height)

    appointments = {get_random_value_hex(32): 1 for _ in range(10)}
    user_info = UserInfo(available_slots=1, subscription_expiry=init_height + 42, appointments=appointments)
    user_id = get_random_value_hex(32)
    monkeypatch.setitem(gatekeeper.registered_users, user_id, user_info)

    # Check that the entry is not in the cache
    target_height = init_height + gatekeeper.expiry_delta + 42
    assert target_height not in gatekeeper.outdated_users_cache

    # Update the cache and check
    gatekeeper.update_outdated_users_cache(target_height)
    cache_entry = gatekeeper.outdated_users_cache.get(target_height)
    # Values is not meant to be used straightaway for checking, but we can flatten it to check it matches
    flattened_appointments = list(flatten(cache_entry.values()))
    assert list(cache_entry.keys()) == [user_id] and flattened_appointments == list(appointments.keys())


def test_update_outdated_users_cache_remove_data(gatekeeper, monkeypatch):
    # Tests how the oldest piece of data is removed after OUTDATED_USERS_CACHE_SIZE_BLOCKS
    # Mock the required BlockProcessor calls from the Gatekeeper
    init_height = 0
    monkeypatch.setattr(gatekeeper.block_processor, "get_block_count", lambda: init_height)

    # Add users that are expiring from the current block to OUTDATED_USERS_CACHE_SIZE_BLOCKS -1 and fill the cache with
    # them
    data = {}
    for i in range(OUTDATED_USERS_CACHE_SIZE_BLOCKS):
        appointments = {get_random_value_hex(32): 1 for _ in range(10)}
        user_info = UserInfo(available_slots=1, subscription_expiry=init_height + i, appointments=appointments)
        user_id = get_random_value_hex(32)
        monkeypatch.setitem(gatekeeper.registered_users, user_id, user_info)

        target_block = init_height + gatekeeper.expiry_delta + i
        gatekeeper.update_outdated_users_cache(target_block)
        # Create a local version of the expected data to compare {block_id: {user_id: [appointment_uuids]}, ...}
        data[target_block] = {user_id: list(appointments.keys())}

    # Check that the cache is full and that each position matches
    assert len(gatekeeper.outdated_users_cache) == OUTDATED_USERS_CACHE_SIZE_BLOCKS
    assert gatekeeper.outdated_users_cache == data

    # Add more blocks and check what data gets kicked (data has an offset of OUTDATED_USERS_CACHE_SIZE_BLOCKS, so we can
    # check if the previous key is there easily)
    for i in range(OUTDATED_USERS_CACHE_SIZE_BLOCKS):
        target_block = init_height + gatekeeper.expiry_delta + OUTDATED_USERS_CACHE_SIZE_BLOCKS + i
        assert target_block - OUTDATED_USERS_CACHE_SIZE_BLOCKS in gatekeeper.outdated_users_cache
        gatekeeper.update_outdated_users_cache(target_block)
        assert target_block - OUTDATED_USERS_CACHE_SIZE_BLOCKS not in gatekeeper.outdated_users_cache


# TESTS WITH BITCOIND UNREACHABLE
# We'll be using a proper BlockProcessor for these tests since we need to be able to test that it does block when
# bitcoind crashes


def test_manage_subscription_expiry_bitcoind_crash(gatekeeper_real_bp, monkeypatch):
    # Test that the data is not deleted until bitcoind comes back online
    current_height = gatekeeper_real_bp.block_processor.get_block_count()

    # Mock the user registration
    user_id = get_random_value_hex(32)
    user_info = UserInfo(available_slots=10, subscription_expiry=current_height + 1)
    monkeypatch.setitem(gatekeeper_real_bp.registered_users, user_id, user_info)

    # Since the gatekeeper is not currently hooked to any ChainMonitor, it won't be notified.
    block_id = generate_blocks(1)[0]

    # Now we can set wrong connection params and feed the block to mock a crash with bitcoind
    monkeypatch.setattr(gatekeeper_real_bp.block_processor, "btc_connect_params", wrong_bitcoind_connect_params)
    gatekeeper_real_bp.block_queue.put(block_id)
    time.sleep(1)

    # The gatekeeper's subscription manager thread should be blocked now. The thread cannot check if the subscription
    # has expired, and the query is blocking
    assert not gatekeeper_real_bp.block_processor.bitcoind_reachable.is_set()
    with pytest.raises(ConnectionRefusedError):
        gatekeeper_real_bp.has_subscription_expired(user_id)

    # Setting the event should unblock the thread and expire the subscription
    monkeypatch.setattr(gatekeeper_real_bp.block_processor, "btc_connect_params", bitcoind_connect_params)
    gatekeeper_real_bp.block_processor.bitcoind_reachable.set()
    time.sleep(1)

    has_subscription_expired, _ = gatekeeper_real_bp.has_subscription_expired(user_id)
    assert has_subscription_expired


def test_add_update_user_bitcoind_crash(gatekeeper_real_bp, gatekeeper_wrong_connection):
    user_id = "02" + get_random_value_hex(32)
    run_test_command_bitcoind_crash(lambda: gatekeeper_wrong_connection.add_update_user(user_id))


def test_has_subscription_expired_bitcoind_crash(gatekeeper_real_bp, gatekeeper_wrong_connection, monkeypatch):
    user_id = "02" + get_random_value_hex(32)
    user_info = UserInfo(available_slots=10, subscription_expiry=1)
    # Add the user to both the gatekeeper's so there's data to check against
    monkeypatch.setitem(gatekeeper_wrong_connection.registered_users, user_id, user_info)
    monkeypatch.setitem(gatekeeper_real_bp.registered_users, user_id, user_info)

    run_test_command_bitcoind_crash(lambda: gatekeeper_wrong_connection.has_subscription_expired(user_id))
