import time
import queue
import pytest
from uuid import uuid4
from copy import deepcopy
from threading import Thread
from coincurve import PrivateKey

from teos.carrier import Receipt
from teos.gatekeeper import UserInfo, AuthenticationFailure, NotEnoughSlots, SubscriptionExpired
from teos.watcher import (
    Watcher,
    AppointmentLimitReached,
    LocatorCache,
    EncryptionError,
    InvalidTransactionFormat,
    AppointmentAlreadyTriggered,
    InvalidParameter,
    AppointmentStatus,
    AppointmentNotFound,
)

import common.receipts as receipts
from common.tools import compute_locator
from common.cryptographer import Cryptographer, hash_160

from test.teos.conftest import (
    config,
    generate_blocks_with_delay,
    mock_generate_blocks,
)
from test.teos.unit.conftest import (
    get_random_value_hex,
    generate_keypair,
    run_test_command_bitcoind_crash,
    run_test_blocking_command_bitcoind_crash,
    mock_connection_refused_return,
    raise_auth_failure,
    raise_not_enough_slots,
    raise_invalid_parameter,
)
from test.teos.unit.mocks import AppointmentsDBM, Gatekeeper, BlockProcessor, Responder


APPOINTMENTS = 5
TEST_SET_SIZE = 200

# Reduce the maximum number of appointments to something we can test faster
MAX_APPOINTMENTS = 100

signing_key, public_key = generate_keypair()
user_sk, user_pk = generate_keypair()
user_id = Cryptographer.get_compressed_pk(user_pk)


@pytest.fixture
def watcher(dbm_mock, gatekeeper_mock, responder_mock, block_processor_mock):
    watcher = Watcher(
        dbm_mock,
        gatekeeper_mock,
        block_processor_mock,
        responder_mock,
        signing_key,
        MAX_APPOINTMENTS,
        config.get("LOCATOR_CACHE_SIZE"),
    )

    return watcher


@pytest.fixture(scope="module")
def txids():
    return [get_random_value_hex(32) for _ in range(100)]


@pytest.fixture(scope="module")
def locator_uuid_map(txids):
    return {compute_locator(txid): uuid4().hex for txid in txids}


def mock_receipt_true(*args, **kwargs):
    return Receipt(True)


def mock_receipt_false(*args, **kwargs):
    return Receipt(False)


# An authenticate_user function that simply does not raise
def authenticate_user_mock(*args, **kwargs):
    return get_random_value_hex(32)


def raise_encryption_error(*args, **kwargs):
    raise EncryptionError("encryption error msg")


def raise_invalid_tx_format(*args, **kwargs):
    raise InvalidTransactionFormat("invalid tx format msg")


# LOCATOR CACHE


def test_locator_cache_init_not_enough_blocks(block_processor_mock, monkeypatch):
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))

    # Mock generating 3 blocks
    blocks = dict()
    mock_generate_blocks(3, blocks, queue.Queue())
    third_block_hash = list(blocks.keys())[2]

    # Mock the interaction with the BlockProcessor based on the mocked blocks
    monkeypatch.setattr(block_processor_mock, "get_block", lambda x, blocking: blocks.get(x))
    locator_cache.init(third_block_hash, block_processor_mock)

    assert len(locator_cache.blocks) == 3
    for k, v in locator_cache.blocks.items():
        assert block_processor_mock.get_block(k, blocking=False)


def test_locator_cache_init(block_processor_mock, monkeypatch):
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))

    # Generate enough blocks so the cache can start full
    blocks = dict()
    mock_generate_blocks(locator_cache.cache_size, blocks, queue.Queue())
    best_block_hash = list(blocks.keys())[-1]

    # Mock the interaction with the BlockProcessor based on the mocked blocks
    monkeypatch.setattr(block_processor_mock, "get_block", lambda x, blocking: blocks.get(x))
    locator_cache.init(best_block_hash, block_processor_mock)

    assert len(locator_cache.blocks) == locator_cache.cache_size
    for k, v in locator_cache.blocks.items():
        assert block_processor_mock.get_block(k, blocking=False)


def test_cache_get_txid():
    # Not much to test here, this is shadowing dict.get
    locator = get_random_value_hex(16)
    txid = get_random_value_hex(32)

    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))
    locator_cache.cache[locator] = txid

    assert locator_cache.get_txid(locator) == txid
    # A random locator should fail
    assert locator_cache.get_txid(get_random_value_hex(16)) is None


def test_update_cache():
    # Update should add data about a new block in the cache. If the cache is full, the oldest block is dropped.
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))

    block_hash = get_random_value_hex(32)
    txs = [get_random_value_hex(32) for _ in range(10)]
    locator_txid_map = {compute_locator(txid): txid for txid in txs}

    # Cache is empty
    assert block_hash not in locator_cache.blocks
    for locator in locator_txid_map.keys():
        assert locator not in locator_cache.cache

    # The data has been added to the cache
    locator_cache.update(block_hash, locator_txid_map)
    assert block_hash in locator_cache.blocks
    for locator in locator_txid_map.keys():
        assert locator in locator_cache.cache


def test_update_cache_full():
    # Updating a full cache should be dropping the oldest block one by one
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))
    block_hashes = []
    big_map = {}

    # Fill the cache first
    for i in range(locator_cache.cache_size):
        block_hash = get_random_value_hex(32)
        txs = [get_random_value_hex(32) for _ in range(10)]
        locator_txid_map = {compute_locator(txid): txid for txid in txs}
        locator_cache.update(block_hash, locator_txid_map)

        if i == 0:
            first_block_hash = block_hash
            first_locator_txid_map = locator_txid_map
        else:
            block_hashes.append(block_hash)
            big_map.update(locator_txid_map)

    # The cache is now full.
    assert first_block_hash in locator_cache.blocks
    for locator in first_locator_txid_map.keys():
        assert locator in locator_cache.cache

    # Add one more
    block_hash = get_random_value_hex(32)
    txs = [get_random_value_hex(32) for _ in range(10)]
    locator_txid_map = {compute_locator(txid): txid for txid in txs}
    locator_cache.update(block_hash, locator_txid_map)

    # The first block is not there anymore, but the rest are there
    assert first_block_hash not in locator_cache.blocks
    for locator in first_locator_txid_map.keys():
        assert locator not in locator_cache.cache

    for block_hash in block_hashes:
        assert block_hash in locator_cache.blocks

    for locator in big_map.keys():
        assert locator in locator_cache.cache


def test_locator_cache_is_full():
    # is_full should return whether the cache is full or not.
    # Create an empty cache
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))

    # Fill it one by one and check it is not full
    for _ in range(locator_cache.cache_size):
        locator_cache.blocks[uuid4().hex] = 0
        assert not locator_cache.is_full()

    # Add one more block and check again, it should be full now
    locator_cache.blocks[uuid4().hex] = 0
    assert locator_cache.is_full()


def test_locator_remove_oldest_block():
    # remove_oldest block should drop the oldest block from the cache.

    # Create an empty caches
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))

    # Add some blocks to the cache
    for _ in range(locator_cache.cache_size):
        txid = get_random_value_hex(32)
        locator = txid[:16]
        locator_cache.blocks[get_random_value_hex(32)] = {locator: txid}
        locator_cache.cache[locator] = txid

    blocks_in_cache = locator_cache.blocks
    oldest_block_hash = list(blocks_in_cache.keys())[0]
    oldest_block_data = blocks_in_cache.get(oldest_block_hash)
    rest_of_blocks = list(blocks_in_cache.keys())[1:]

    # Remove the block
    locator_cache.remove_oldest_block()

    # The oldest block data is not in the cache anymore
    assert oldest_block_hash not in locator_cache.blocks
    for locator in oldest_block_data:
        assert locator not in locator_cache.cache

    # The rest of data is in the cache
    assert set(rest_of_blocks).issubset(locator_cache.blocks)
    for block_hash in rest_of_blocks:
        for locator in locator_cache.blocks[block_hash]:
            assert locator in locator_cache.cache


def test_fix_cache(block_processor_mock, monkeypatch):
    # This tests how a reorg will create a new version of the cache
    # Let's start setting a full cache. We'll mine ``cache_size`` bocks to be sure it's full
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))

    # We'll need two additional blocks since we'll rollback the chain into the past
    blocks = dict()
    mock_generate_blocks(locator_cache.cache_size + 2, blocks, queue.Queue())
    best_block_hash = list(blocks.keys())[-1]

    # Mock the interaction with the BlockProcessor based on the mocked blocks
    monkeypatch.setattr(block_processor_mock, "get_block", lambda x, blocking: blocks.get(x))
    monkeypatch.setattr(block_processor_mock, "get_block_count", lambda: len(blocks))

    locator_cache.init(best_block_hash, block_processor_mock)
    assert len(locator_cache.blocks) == locator_cache.cache_size

    # Now let's fake a reorg of less than ``cache_size``. We'll go two blocks into the past.
    current_tip = best_block_hash
    current_tip_locators = locator_cache.blocks[current_tip]
    current_tip_parent = block_processor_mock.get_block(current_tip, False).get("previousblockhash")
    current_tip_parent_locators = locator_cache.blocks[current_tip_parent]
    fake_tip = block_processor_mock.get_block(current_tip_parent, False).get("previousblockhash")
    locator_cache.fix(fake_tip, block_processor_mock)

    # The last two blocks are not in the cache nor are there any of its locators
    assert current_tip not in locator_cache.blocks and current_tip_parent not in locator_cache.blocks
    for locator in current_tip_parent_locators + current_tip_locators:
        assert locator not in locator_cache.cache

    # The fake tip is the new tip, and two additional blocks are at the bottom
    assert fake_tip in locator_cache.blocks and list(locator_cache.blocks.keys())[-1] == fake_tip
    assert len(locator_cache.blocks) == locator_cache.cache_size

    # Test the same for a full cache reorg. We can simulate this by adding more blocks than the cache can fit and
    # trigger a fix. We'll use a new cache to compare with the old
    old_cache_blocks = deepcopy(locator_cache.blocks)

    mock_generate_blocks(locator_cache.cache_size, blocks, queue.Queue())
    best_block_hash = list(blocks.keys())[-1]
    locator_cache.fix(best_block_hash, block_processor_mock)

    # None of the data from the old cache is in the new cache
    for block_hash, locators in old_cache_blocks.items():
        assert block_hash not in locator_cache.blocks
        for locator in locators:
            assert locator not in locator_cache.cache

    # The data in the new cache corresponds to the last ``cache_size`` blocks.
    block_count = block_processor_mock.get_block_count()
    for i in range(block_count, block_count - locator_cache.cache_size, -1):
        block_hash = list(blocks.keys())[i - 1]
        assert block_hash in locator_cache.blocks
        for locator in locator_cache.blocks[block_hash]:
            assert locator in locator_cache.cache


# WATCHER


def test_watcher_init(watcher):
    assert isinstance(watcher.appointments, dict) and len(watcher.appointments) == 0
    assert isinstance(watcher.locator_uuid_map, dict) and len(watcher.locator_uuid_map) == 0
    assert watcher.block_queue.empty()
    assert isinstance(watcher.db_manager, AppointmentsDBM)
    assert isinstance(watcher.gatekeeper, Gatekeeper)
    assert isinstance(watcher.block_processor, BlockProcessor)
    assert isinstance(watcher.responder, Responder)
    assert isinstance(watcher.max_appointments, int)
    assert isinstance(watcher.signing_key, PrivateKey)
    assert isinstance(watcher.locator_cache, LocatorCache)


def test_awake(watcher, monkeypatch):
    # Tests that the Watcher's do_watch thread is launch when awake is called

    # Mock the last known block and generate one on top
    blocks = {}
    watcher.last_known_block = get_random_value_hex(32)
    monkeypatch.setattr(watcher.block_processor, "get_block", lambda x, blocking: blocks.get(x))
    mock_generate_blocks(1, blocks, watcher.block_queue, watcher.last_known_block)

    # Check that, before awaking the Watcher, the data is not processed
    assert not watcher.block_queue.empty()
    assert watcher.block_queue.unfinished_tasks == 1

    # Awake the Watcher and check again
    do_watch_thread = watcher.awake()
    time.sleep(1)

    assert do_watch_thread.is_alive()
    assert watcher.block_queue.empty()
    assert watcher.block_queue.unfinished_tasks == 0


def test_register(watcher, monkeypatch):
    # Register requests should work as long as the provided user_id is valid and bitcoind is reachable

    # Mock the interaction with the Gatekeeper
    slots = 100
    expiry = 200
    receipt = bytes.fromhex(get_random_value_hex(70))
    monkeypatch.setattr(watcher.gatekeeper, "add_update_user", lambda x: (slots, expiry, receipt))

    # Request a registration and check the response
    available_slots, subscription_expiry, signature = watcher.register(user_id)
    assert available_slots == slots
    assert subscription_expiry == expiry
    assert Cryptographer.recover_pk(receipt, signature) == watcher.signing_key.public_key


def test_register_wrong_data(watcher, monkeypatch):
    # If the provided user_id does not match the expected format, register will fail

    # Mock the interaction with the Gatekeeper as if the provided data was wrong
    monkeypatch.setattr(watcher.gatekeeper, "add_update_user", raise_invalid_parameter)
    with pytest.raises(InvalidParameter):
        watcher.register(get_random_value_hex(32))


def test_get_appointment(watcher, generate_dummy_appointment, generate_dummy_tracker, monkeypatch):
    # Get appointment should return back data as long a the user does have the requested appointment
    locator = get_random_value_hex(32)
    signature = get_random_value_hex(71)
    uuid = hash_160("{}{}".format(locator, user_id))

    # Mock the user being registered
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, 1))

    # The appointment can either be in the Watcher of the Responder, mock the former case
    appointment = generate_dummy_appointment()
    monkeypatch.setitem(watcher.appointments, uuid, appointment)
    monkeypatch.setattr(watcher.db_manager, "load_watcher_appointment", lambda x: appointment.to_dict())

    # Request and check
    appointment_data, status = watcher.get_appointment(locator, signature)
    assert appointment_data == appointment.to_dict()
    assert status == AppointmentStatus.BEING_WATCHED

    # Do the same for the appointment being in the Responder
    monkeypatch.delitem(watcher.appointments, uuid)
    tracker = generate_dummy_tracker()
    monkeypatch.setattr(watcher.responder, "has_tracker", lambda x: True)
    monkeypatch.setattr(watcher.db_manager, "load_responder_tracker", lambda x: tracker.to_dict())

    # Request and check
    tracker_data, status = watcher.get_appointment(locator, signature)
    assert tracker_data == tracker.to_dict()
    assert status == AppointmentStatus.DISPUTE_RESPONDED


def test_get_appointment_non_registered(watcher, monkeypatch):
    # If the user is not registered, an authentication error will be returned
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", raise_auth_failure)

    locator = get_random_value_hex(32)
    signature = get_random_value_hex(71)
    with pytest.raises(AuthenticationFailure):
        watcher.get_appointment(locator, signature)


def test_get_appointment_wrong_user_or_appointment(watcher, monkeypatch):
    # Appointments are stored in the using a uuid computed as a hash of locator | user_id. If the appointment does not
    # exist for the given user, NOT FOUND will be returned.

    # This one is easy to test, since simply not adding data to the structures does the trick. Just mock the user
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, 1))

    locator = get_random_value_hex(32)
    signature = get_random_value_hex(71)
    with pytest.raises(AppointmentNotFound, match=f"Cannot find {locator}"):
        watcher.get_appointment(locator, signature)


def test_get_appointment_subscription_error(watcher, monkeypatch):
    # If the subscription has expired, the user won't be allowed to request data

    # Mock and expired user
    expiry = 100
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (True, expiry))

    locator = get_random_value_hex(32)
    signature = get_random_value_hex(71)
    with pytest.raises(SubscriptionExpired, match=f"Your subscription expired at block {expiry}"):
        watcher.get_appointment(locator, signature)


def test_add_appointment_non_registered(watcher, generate_dummy_appointment, monkeypatch):
    # Appointments from non-registered users should fail
    appointment = generate_dummy_appointment()

    # Mock the return from the Gatekeeper (user not registered)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", raise_auth_failure)

    with pytest.raises(AuthenticationFailure, match="Auth failure msg"):
        watcher.add_appointment(appointment, appointment.user_signature)


def test_add_appointment_no_slots(watcher, generate_dummy_appointment, monkeypatch):
    # Appointments from register users with no available slots should aso fail

    # Mock a registered user with no enough slots (we need to mock all the way up to add_update_appointment)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, 0))
    monkeypatch.setattr(watcher.responder, "has_tracker", lambda x: False)
    monkeypatch.setattr(watcher.gatekeeper, "add_update_appointment", raise_not_enough_slots)

    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    with pytest.raises(NotEnoughSlots):
        watcher.add_appointment(appointment, appointment_signature)


def test_add_appointment_expired_subscription(watcher, generate_dummy_appointment, monkeypatch):
    # Appointments from registered users with expired subscriptions fail as well

    # Mock a registered user with expired subscription
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (True, 42))

    appointment = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    with pytest.raises(SubscriptionExpired, match="Your subscription expired at block"):
        watcher.add_appointment(appointment, appointment_signature)


def test_add_appointment(watcher, generate_dummy_appointment, monkeypatch):
    # A registered user with no subscription issues should be able to add an appointment
    appointment = generate_dummy_appointment()

    # Mock a registered user
    expiry = 100
    user_info = UserInfo(MAX_APPOINTMENTS, expiry)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, expiry))
    monkeypatch.setattr(watcher.responder, "has_tracker", lambda x: False)
    monkeypatch.setattr(watcher.gatekeeper, "add_update_appointment", lambda x, y, z: MAX_APPOINTMENTS - 1)
    monkeypatch.setattr(watcher.gatekeeper, "get_user_info", lambda x: user_info)

    response = watcher.add_appointment(appointment, appointment.user_signature)
    assert response.get("locator") == appointment.locator
    assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
        Cryptographer.recover_pk(
            receipts.create_appointment_receipt(appointment.user_signature, response.get("start_block")),
            response.get("signature"),
        )
    )

    # Check that we can also add an already added appointment (same locator)
    response = watcher.add_appointment(appointment, appointment.user_signature)
    assert response.get("locator") == appointment.locator
    assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
        Cryptographer.recover_pk(
            receipts.create_appointment_receipt(appointment.user_signature, response.get("start_block")),
            response.get("signature"),
        )
    )
    # One one copy is kept since the appointments were the same
    # (the slot count should have not been reduced, but that's something to be tested in the Gatekeeper)
    assert len(watcher.locator_uuid_map[appointment.locator]) == 1

    # If two appointments with the same locator come from different users, they are kept.
    another_user_sk, another_user_pk = generate_keypair()
    another_user_id = Cryptographer.get_compressed_pk(another_user_pk)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: another_user_id)

    appointment_signature = Cryptographer.sign(appointment.serialize(), another_user_sk)
    response = watcher.add_appointment(appointment, appointment_signature)
    assert response.get("locator") == appointment.locator
    assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
        Cryptographer.recover_pk(
            receipts.create_appointment_receipt(appointment_signature, response.get("start_block")),
            response.get("signature"),
        )
    )
    assert len(watcher.locator_uuid_map[appointment.locator]) == 2


def test_add_appointment_in_cache(watcher, generate_dummy_appointment_w_trigger, monkeypatch):
    # Adding an appointment which trigger is in the cache should be accepted
    appointment, commitment_txid = generate_dummy_appointment_w_trigger()
    # We need the blob and signature to be valid
    appointment.user_signature = Cryptographer.sign(appointment.encrypted_blob.encode(), user_sk)

    # Mock the transaction being in the cache and all the way until sending it to the Responder
    expiry = 100
    user_info = UserInfo(MAX_APPOINTMENTS, expiry)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, expiry))
    monkeypatch.setattr(watcher.gatekeeper, "get_user_info", lambda x: user_info)
    monkeypatch.setattr(watcher.locator_cache, "get_txid", lambda x: commitment_txid)
    monkeypatch.setattr(watcher.responder, "handle_breach", mock_receipt_true)

    # Try to add the appointment
    # user_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    response = watcher.add_appointment(appointment, appointment.user_signature)
    appointment_receipt = receipts.create_appointment_receipt(appointment.user_signature, response.get("start_block"))

    # The appointment is accepted but it's not in the Watcher
    assert (
        response
        and response.get("locator") == appointment.locator
        and Cryptographer.get_compressed_pk(watcher.signing_key.public_key)
        == Cryptographer.get_compressed_pk(Cryptographer.recover_pk(appointment_receipt, response.get("signature")))
    )
    assert not watcher.locator_uuid_map.get(appointment.locator)

    # It went to the Responder straightaway, we can check this by querying the database
    for uuid, db_appointment in watcher.db_manager.load_watcher_appointments(include_triggered=True).items():
        if db_appointment.get("locator") == appointment.locator:
            assert uuid in watcher.db_manager.load_all_triggered_flags()

    # Trying to send it again should fail since it is already in the Responder
    monkeypatch.setattr(watcher.responder, "has_tracker", lambda x: True)
    with pytest.raises(AppointmentAlreadyTriggered):
        watcher.add_appointment(appointment, Cryptographer.sign(appointment.serialize(), user_sk))


def test_add_appointment_in_cache_invalid_blob_or_tx(watcher, generate_dummy_appointment_w_trigger, monkeypatch):
    # Trying to add an appointment with invalid data (blob does not decrypt to a tx or the tx in not invalid) with a
    # trigger in the cache will be accepted, but the data will de dropped.

    appointment, commitment_txid = generate_dummy_appointment_w_trigger()

    # Mock the trigger being in the cache
    expiry = 100
    user_info = UserInfo(MAX_APPOINTMENTS, expiry)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, expiry))
    monkeypatch.setattr(watcher.gatekeeper, "get_user_info", lambda x: user_info)
    monkeypatch.setattr(watcher.locator_cache, "get_txid", lambda x: commitment_txid)

    # Check for both the blob being invalid, and the transaction being invalid
    for mocked_return in [raise_encryption_error, raise_invalid_tx_format]:
        # Mock the data check (invalid blob)
        monkeypatch.setattr(watcher.responder, "handle_breach", mocked_return)

        # Try to add the appointment
        response = watcher.add_appointment(appointment, appointment.user_signature)
        appointment_receipt = receipts.create_appointment_receipt(
            appointment.user_signature, response.get("start_block")
        )

        # The appointment is accepted but dropped
        assert (
            response
            and response.get("locator") == appointment.locator
            and Cryptographer.get_compressed_pk(watcher.signing_key.public_key)
            == Cryptographer.get_compressed_pk(Cryptographer.recover_pk(appointment_receipt, response.get("signature")))
        )

        # Check the appointment didn't go to the Responder (by checking there are no triggered flags)
        assert watcher.db_manager.load_all_triggered_flags() == []


def test_add_too_many_appointments(watcher, generate_dummy_appointment, monkeypatch):
    # Adding appointment beyond the user limit should fail

    # Mock the user being registered
    expiry = 100
    user_info = UserInfo(MAX_APPOINTMENTS, expiry)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, expiry))
    monkeypatch.setattr(watcher.gatekeeper, "get_user_info", lambda x: user_info)

    for i in range(user_info.available_slots):
        appointment = generate_dummy_appointment()
        response = watcher.add_appointment(appointment, appointment.user_signature)
        appointment_receipt = receipts.create_appointment_receipt(
            appointment.user_signature, response.get("start_block")
        )

        assert response.get("locator") == appointment.locator
        assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
            Cryptographer.recover_pk(appointment_receipt, response.get("signature"))
        )

    with pytest.raises(AppointmentLimitReached):
        appointment = generate_dummy_appointment()
        appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
        watcher.add_appointment(appointment, appointment_signature)


def test_do_watch(watcher, generate_dummy_appointment_w_trigger, monkeypatch):
    # do_watch creates a thread in charge of watching for breaches. It also triggers data deletion when necessary, based
    # in the block height of the received blocks.
    # Test the following:
    # - Adding transactions to the Watcher and trigger them
    # - Check triggered appointments are removed from the Watcher
    # - Outdate appointments and check they are also removed

    # Mock the user being registered
    expiry = 100
    user_info = UserInfo(MAX_APPOINTMENTS, expiry)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, expiry))
    monkeypatch.setattr(watcher.gatekeeper, "get_user_info", lambda x: user_info)

    # Mock the interactions with the Gatekeeper
    monkeypatch.setattr(watcher.gatekeeper, "get_outdated_appointments", lambda x: [])
    monkeypatch.setattr(watcher.responder, "handle_breach", mock_receipt_true)

    # Add the appointments to the tower. We add them instead of mocking to avoid having to mock all the data structures
    # plus database
    commitment_txids = []
    triggered_valid = []
    for i in range(APPOINTMENTS):
        appointment, commitment_txid = generate_dummy_appointment_w_trigger()
        watcher.add_appointment(appointment, appointment.user_signature)
        commitment_txids.append(commitment_txid)

        uuid = hash_160("{}{}".format(appointment.locator, user_id))
        if i < 2:
            triggered_valid.append(uuid)

    # Start the watching thread
    do_watch_thread = Thread(target=watcher.do_watch, daemon=True)
    do_watch_thread.start()

    # Mock a new block with the two first triggers in it
    block_id = get_random_value_hex(32)
    block = {"tx": commitment_txids[:2], "height": 1}
    monkeypatch.setattr(watcher.block_processor, "get_block", lambda x, blocking: block)
    watcher.block_queue.put(block_id)
    time.sleep(0.2)

    # After generating a block, the appointment count should have been reduced by 2 (two breaches)
    assert len(watcher.appointments) == APPOINTMENTS - 2

    # This two first should have gone to the Responder, we can check the trigger flags to validate
    assert set(watcher.db_manager.load_all_triggered_flags()) == set(triggered_valid)

    # Mock two more transactions being triggered, this time with invalid data
    monkeypatch.setattr(watcher.responder, "handle_breach", mock_receipt_false)
    block_id = get_random_value_hex(32)
    block = {"tx": commitment_txids[2:4], "height": 2}
    monkeypatch.setattr(watcher.block_processor, "get_block", lambda x, blocking: block)
    watcher.block_queue.put(block_id)
    time.sleep(0.2)

    # Two more appointments should be gone but none of them should have gone trough the Responder
    assert len(watcher.appointments) == APPOINTMENTS - 4
    # Check the triggers are the same as before
    assert set(watcher.db_manager.load_all_triggered_flags()) == set(triggered_valid)

    # The rest of appointments will timeout after the subscription timesout
    monkeypatch.setattr(watcher.gatekeeper, "get_outdated_appointments", lambda x: list(watcher.appointments.keys()))
    mock_generate_blocks(1, {}, watcher.block_queue)
    assert len(watcher.appointments) == 0


def test_do_watch_cache_update(watcher, block_processor_mock, monkeypatch):
    # The do_watch thread is also in charge of keeping the locator cache up to date. Test that adding mining a new block
    # removed the oldest block from the cache and add the new data to it.

    # Start the watching thread
    do_watch_thread = Thread(target=watcher.do_watch, daemon=True)
    do_watch_thread.start()

    # Generate enough blocks so the cache can start full
    blocks = dict()
    mock_generate_blocks(watcher.locator_cache.cache_size, blocks, watcher.block_queue)

    # Mock the interaction with the BlockProcessor based on the mocked blocks
    monkeypatch.setattr(block_processor_mock, "get_block", lambda x, blocking: blocks.get(x))

    for _ in range(10):
        blocks_in_cache = watcher.locator_cache.blocks
        oldest_block_hash = list(blocks_in_cache.keys())[0]
        oldest_block_data = blocks_in_cache.get(oldest_block_hash)
        rest_of_blocks = list(blocks_in_cache.keys())[1:]
        assert len(watcher.locator_cache.blocks) == watcher.locator_cache.cache_size

        # Mock a block on top of the last tip
        mock_generate_blocks(1, blocks, watcher.block_queue, prev_block_hash=list(blocks.keys())[-1])

        # The last oldest block is gone but the rest remain
        assert oldest_block_hash not in watcher.locator_cache.blocks
        assert set(rest_of_blocks).issubset(watcher.locator_cache.blocks.keys())

        # The locators of the oldest block are gone but the rest remain
        for locator in oldest_block_data:
            assert locator not in watcher.locator_cache.cache
        for block_hash in rest_of_blocks:
            for locator in watcher.locator_cache.blocks[block_hash]:
                assert locator in watcher.locator_cache.cache

        # The size of the cache is the same
        assert len(watcher.locator_cache.blocks) == watcher.locator_cache.cache_size


def test_get_breaches(watcher, txids, locator_uuid_map):
    # Get breaches returns a dictionary (locator:txid) of breaches given a map of locator:txid.
    # Test that it works with valid data

    # Create a locator_uuid_map and a locators_txid_map that fully match
    watcher.locator_uuid_map = locator_uuid_map
    locators_txid_map = {compute_locator(txid): txid for txid in txids}

    # All the txids must breach
    potential_breaches = watcher.get_breaches(locators_txid_map)
    assert locator_uuid_map.keys() == potential_breaches.keys()


def test_get_breaches_random_data(watcher, locator_uuid_map):
    # The likelihood of finding a potential breach with random data should be negligible
    watcher.locator_uuid_map = locator_uuid_map
    txids = [get_random_value_hex(32) for _ in range(TEST_SET_SIZE)]
    locators_txid_map = {compute_locator(txid): txid for txid in txids}

    potential_breaches = watcher.get_breaches(locators_txid_map)

    # None of the txids should breach
    assert len(potential_breaches) == 0


def test_check_breach(watcher, generate_dummy_appointment_w_trigger):
    # A breach will be flagged as valid only if the encrypted blob can be properly decrypted and the resulting data
    # matches a transaction format.
    uuid = uuid4().hex
    appointment, dispute_txid = generate_dummy_appointment_w_trigger()

    penalty_txid, penalty_rawtx = watcher.check_breach(uuid, appointment, dispute_txid)
    assert Cryptographer.encrypt(penalty_rawtx, dispute_txid) == appointment.encrypted_blob


def test_check_breach_random_data(watcher, generate_dummy_appointment_w_trigger, monkeypatch):
    # If a breach triggers an appointment with random data as encrypted blob, the check should fail.
    uuid = uuid4().hex
    appointment, dispute_txid = generate_dummy_appointment_w_trigger()

    # Mock the interaction with the Cryptographer when trying to decrypt a blob
    monkeypatch.setattr(Cryptographer, "decrypt", raise_encryption_error)

    with pytest.raises(EncryptionError):
        watcher.check_breach(uuid, appointment, dispute_txid)


def test_check_breach_invalid_transaction(watcher, generate_dummy_appointment_w_trigger, monkeypatch):
    # If the breach triggers an appointment with data that can be decrypted but does not match a transaction, it should
    # fail
    uuid = uuid4().hex
    appointment, dispute_txid = generate_dummy_appointment_w_trigger()

    # Mock the interaction with the BlockProcessor when trying to decode a transaction
    monkeypatch.setattr(watcher.block_processor, "decode_raw_transaction", raise_invalid_tx_format)

    with pytest.raises(InvalidTransactionFormat):
        watcher.check_breach(uuid, appointment, dispute_txid)


def test_filter_valid_breaches(watcher, generate_dummy_appointment_w_trigger, monkeypatch):
    # filter_breaches returns computes two collections, one with the valid breaches (breaches that properly decrypt
    # appointments) and one with invalid ones. Test it with a single valid breach.

    # Create a new appointment
    dummy_appointment, dispute_txid = generate_dummy_appointment_w_trigger()

    # Mock the interaction with the Gatekeeper. We'll the appointment to the Watcher instead of mocking all the
    # structures + db
    expiry = 100
    user_info = UserInfo(MAX_APPOINTMENTS, expiry)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, expiry))
    monkeypatch.setattr(watcher.gatekeeper, "get_user_info", lambda x: user_info)
    watcher.add_appointment(dummy_appointment, dummy_appointment.user_signature)

    # Filter the data and check
    potential_breaches = {dummy_appointment.locator: dispute_txid}
    valid_breaches, invalid_breaches = watcher.filter_breaches(potential_breaches)

    # We have "triggered" a single breach and it was valid.
    assert len(invalid_breaches) == 0 and len(valid_breaches) == 1


def test_filter_breaches_random_data(watcher, generate_dummy_appointment_w_trigger, monkeypatch):
    # Filtering breaches with random data should return all invalid breaches
    potential_breaches = {}

    # Mock the interaction with the Gatekeeper. We'll the appointment to the Watcher instead of mocking all the
    # structures + db
    expiry = 100
    user_info = UserInfo(MAX_APPOINTMENTS, expiry)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, expiry))
    monkeypatch.setattr(watcher.gatekeeper, "get_user_info", lambda x: user_info)

    for i in range(TEST_SET_SIZE // 2):
        dummy_appointment, dispute_txid = generate_dummy_appointment_w_trigger()

        # Only half of the data will be tagged as a breach
        if i % 2:
            dispute_txid = get_random_value_hex(32)
            potential_breaches[dummy_appointment.locator] = dispute_txid

        watcher.add_appointment(dummy_appointment, dummy_appointment.user_signature)

    # Filter the data and check
    valid_breaches, invalid_breaches = watcher.filter_breaches(potential_breaches)

    # We have "triggered" TEST_SET_SIZE/4 breaches, all of them invalid.
    assert len(valid_breaches) == 0 and len(invalid_breaches) == TEST_SET_SIZE // 4


def test_get_subscription_info(watcher, generate_dummy_appointment, generate_dummy_tracker, monkeypatch):
    # Tests how get_subscription_info should return no data for empty subscriptions, and the info matching the
    # subscriptions otherwise.

    # Mock a registered user
    available_slots = MAX_APPOINTMENTS
    subscription_expiry = 100
    user_info = UserInfo(available_slots, subscription_expiry)
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (False, subscription_expiry))
    monkeypatch.setattr(watcher.gatekeeper, "get_user_info", lambda x: user_info)

    message = "get subscription info"
    signature = Cryptographer.sign(message.encode("utf-8"), user_sk)

    # Empty subscription
    sub_info, locators = watcher.get_subscription_info(signature)
    assert len(locators) == 0
    assert sub_info.available_slots == available_slots
    assert sub_info.subscription_expiry == subscription_expiry

    # Generate some subscription data
    uuid = uuid4().hex
    uuid2 = uuid4().hex
    appointment = generate_dummy_appointment()
    tracker = generate_dummy_tracker()

    # Mock the Watcher, Responder and Gatekeeper's data structures
    monkeypatch.setattr(watcher, "appointments", {uuid: appointment.get_summary()})
    monkeypatch.setattr(watcher.responder, "trackers", {uuid2: tracker.get_summary()})
    user_info.appointments = {uuid: 1, uuid2: 1}

    # And the interaction with the Responder
    monkeypatch.setattr(watcher.responder, "has_tracker", lambda x: True)
    monkeypatch.setattr(watcher.responder, "get_tracker", lambda x: tracker.get_summary())

    sub_info, locators = watcher.get_subscription_info(signature)
    assert set(locators) == {appointment.locator, tracker.locator}
    assert sub_info.available_slots == available_slots
    assert sub_info.subscription_expiry == subscription_expiry


def test_get_subscription_info_non_registered(watcher, monkeypatch):
    # If the user is not registered, an authentication error will be returned
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", raise_auth_failure)

    signature = get_random_value_hex(71)
    with pytest.raises(AuthenticationFailure):
        watcher.get_subscription_info(signature)


def test_get_subscription_info_subscription_error(watcher, monkeypatch):
    # If the subscription has expired, the user won't be allowed to request data

    # Mock and expired user
    expiry = 100
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", lambda x, y: user_id)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", lambda x: (True, expiry))

    signature = get_random_value_hex(71)
    with pytest.raises(SubscriptionExpired, match=f"Your subscription expired at block {expiry}"):
        watcher.get_subscription_info(signature)


# TESTS WITH BITCOIND UNREACHABLE.
# There are two approaches for the following tests:
#   - For blocking functionality we check that the command does not raise (but block) and that after the blocking event
#     is set, the command returns.
#   - For non-blocking functionality we check that the command raises


def test_locator_cache_init_bitcoind_crash(block_processor):
    # A real BlockProcessor is required to test blocking functionality, since the mock does not implement that stuff
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))

    run_test_blocking_command_bitcoind_crash(
        block_processor.bitcoind_reachable,
        lambda: locator_cache.init(block_processor.get_best_block_hash(), block_processor),
    )


def test_fix_cache_bitcoind_crash(block_processor):
    # A real BlockProcessor is required to test blocking functionality, since the mock does not implement that stuff
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))

    run_test_blocking_command_bitcoind_crash(
        block_processor.bitcoind_reachable,
        lambda: locator_cache.fix(block_processor.get_best_block_hash(), block_processor),
    )


def test_register_bitcoind_crash(watcher, monkeypatch):
    monkeypatch.setattr(watcher.gatekeeper, "add_update_user", mock_connection_refused_return)

    run_test_command_bitcoind_crash(lambda: watcher.register(get_random_value_hex(32)))


def test_get_appointment_bitcoind_crash(watcher, monkeypatch):
    # We don't need to get the right user, just not to fail, checking if a subscription has expired will return
    # ConnectionRefusedError, which is what we need to test for.
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", authenticate_user_mock)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", mock_connection_refused_return)

    run_test_command_bitcoind_crash(lambda: watcher.get_appointment(get_random_value_hex(32), get_random_value_hex(32)))


def test_add_appointment_bitcoind_crash(watcher, generate_dummy_appointment, monkeypatch):
    # Same as with the previous test, we just need to check that the ConnectionRefusedError raised by
    # has_subscription_expired is forwarded.
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", authenticate_user_mock)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", mock_connection_refused_return)

    appointment = generate_dummy_appointment()
    run_test_command_bitcoind_crash(lambda: watcher.add_appointment(appointment, get_random_value_hex(73)))


def test_get_subscription_info_bitcoind_crash(watcher, monkeypatch):
    # Same approach as the two previous tests
    monkeypatch.setattr(watcher.gatekeeper, "authenticate_user", authenticate_user_mock)
    monkeypatch.setattr(watcher.gatekeeper, "has_subscription_expired", mock_connection_refused_return)

    run_test_command_bitcoind_crash(lambda: watcher.get_subscription_info(get_random_value_hex(73)))


def test_do_watch_bitcoind_crash(watcher, block_processor):
    # A real BlockProcessor is required to test blocking functionality, since the mock does not implement that stuff
    # Let's start to watch
    watcher.block_processor = block_processor
    do_watch_thread = Thread(target=watcher.do_watch, daemon=True)
    do_watch_thread.start()
    time.sleep(2)

    # Block the watcher
    watcher.block_processor.bitcoind_reachable.clear()
    assert watcher.block_queue.empty()

    # Mine a block and check how the Watcher is blocked processing it
    best_tip = generate_blocks_with_delay(1, 2)[0]
    watcher.block_queue.put(best_tip)
    time.sleep(2)
    assert watcher.last_known_block != best_tip
    assert watcher.block_queue.unfinished_tasks == 1

    # Reestablish the connection and check back
    watcher.block_processor.bitcoind_reachable.set()
    time.sleep(2)
    assert watcher.last_known_block == best_tip
    assert watcher.block_queue.unfinished_tasks == 0


def test_check_breach_bitcoind_crash(watcher, block_processor, generate_dummy_appointment_w_trigger, monkeypatch):
    uuid = uuid4().hex
    appointment, dispute_txid = generate_dummy_appointment_w_trigger()

    # A real BlockProcessor is required to test blocking functionality, since the mock does not implement that stuff
    # We also need to  mock decoding the transaction given we're using dummy data
    watcher.block_processor = block_processor
    monkeypatch.setattr(block_processor, "decode_raw_transaction", lambda x, blocking: {})

    run_test_blocking_command_bitcoind_crash(
        watcher.block_processor.bitcoind_reachable, lambda: watcher.check_breach(uuid, appointment, dispute_txid)
    )
