import pytest
from uuid import uuid4
from shutil import rmtree
from copy import deepcopy
from threading import Thread
from coincurve import PrivateKey

from teos.carrier import Carrier
from teos.responder import Responder
from teos.gatekeeper import UserInfo
from teos.chain_monitor import ChainMonitor
from teos.block_processor import BlockProcessor
from teos.appointments_dbm import AppointmentsDBM
from teos.gatekeeper import Gatekeeper, AuthenticationFailure, NotEnoughSlots
from teos.watcher import (
    Watcher,
    AppointmentLimitReached,
    LocatorCache,
    EncryptionError,
    InvalidTransactionFormat,
    AppointmentAlreadyTriggered,
)

import common.receipts as receipts
from common.tools import compute_locator
from common.appointment import Appointment
from common.cryptographer import Cryptographer

from test.teos.conftest import (
    config,
    generate_blocks,
    generate_blocks_with_delay,
    create_txs,
    bitcoin_cli,
    generate_block_with_transactions,
)
from test.teos.unit.conftest import (
    get_random_value_hex,
    generate_keypair,
    bitcoind_feed_params,
    bitcoind_connect_params,
)

APPOINTMENTS = 5
TEST_SET_SIZE = 200

signing_key, public_key = generate_keypair()

# Reduce the maximum number of appointments to something we can test faster
MAX_APPOINTMENTS = 100


@pytest.fixture(scope="session")
def temp_db_manager():
    db_name = get_random_value_hex(8)
    db_manager = AppointmentsDBM(db_name)

    yield db_manager

    db_manager.db.close()
    rmtree(db_name)


@pytest.fixture(scope="module")
def watcher(run_bitcoind, db_manager, gatekeeper):
    block_processor = BlockProcessor(bitcoind_connect_params)
    carrier = Carrier(bitcoind_connect_params)

    responder = Responder(db_manager, gatekeeper, carrier, block_processor)
    watcher = Watcher(
        db_manager,
        gatekeeper,
        block_processor,
        responder,
        signing_key,
        MAX_APPOINTMENTS,
        config.get("LOCATOR_CACHE_SIZE"),
    )

    watcher.last_known_block = block_processor.get_best_block_hash()

    chain_monitor = ChainMonitor(
        watcher.block_queue, watcher.responder.block_queue, block_processor, bitcoind_feed_params
    )
    chain_monitor.monitor_chain()

    return watcher


@pytest.fixture(scope="module")
def txids():
    return [get_random_value_hex(32) for _ in range(100)]


@pytest.fixture(scope="module")
def locator_uuid_map(txids):
    return {compute_locator(txid): uuid4().hex for txid in txids}


# FIXME: 194 will do with dummy appointment
def create_appointments(generate_dummy_appointment, n):
    locator_uuid_map = dict()
    appointments = dict()
    dispute_txs = []

    for i in range(n):
        appointment, dispute_tx = generate_dummy_appointment()
        uuid = uuid4().hex

        appointments[uuid] = appointment
        locator_uuid_map[appointment.locator] = [uuid]
        dispute_txs.append(dispute_tx)

    return appointments, locator_uuid_map, dispute_txs


def test_locator_cache_init_not_enough_blocks(block_processor):
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))
    # Make sure there are at least 3 blocks
    block_count = block_processor.get_block_count()
    if block_count < 3:
        generate_blocks(3 - block_count)

    # Simulate there are only 3 blocks
    third_block_hash = bitcoin_cli.getblockhash(2)
    locator_cache.init(third_block_hash, block_processor)
    assert len(locator_cache.blocks) == 3
    for k, v in locator_cache.blocks.items():
        assert block_processor.get_block(k)


def test_locator_cache_init(block_processor):
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))

    # Generate enough blocks so the cache can start full
    generate_blocks(2 * locator_cache.cache_size)

    locator_cache.init(block_processor.get_best_block_hash(), block_processor)
    assert len(locator_cache.blocks) == locator_cache.cache_size
    for k, v in locator_cache.blocks.items():
        assert block_processor.get_block(k)


def test_get_txid():
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
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))
    block_hashes = []
    big_map = {}

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
    # Empty cache
    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))

    for _ in range(locator_cache.cache_size):
        locator_cache.blocks[uuid4().hex] = 0
        assert not locator_cache.is_full()

    locator_cache.blocks[uuid4().hex] = 0
    assert locator_cache.is_full()


def test_locator_remove_oldest_block():
    # Empty cache
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
    locator_cache.remove_oldest_block()

    # Oldest block data is not in the cache
    assert oldest_block_hash not in locator_cache.blocks
    for locator in oldest_block_data:
        assert locator not in locator_cache.cache

    # The rest of data is in the cache
    assert set(rest_of_blocks).issubset(locator_cache.blocks)
    for block_hash in rest_of_blocks:
        for locator in locator_cache.blocks[block_hash]:
            assert locator in locator_cache.cache


def test_fix_cache(block_processor):
    # This tests how a reorg will create a new version of the cache
    # Let's start setting a full cache. We'll mine ``cache_size`` bocks to be sure it's full
    generate_blocks(config.get("LOCATOR_CACHE_SIZE"))

    locator_cache = LocatorCache(config.get("LOCATOR_CACHE_SIZE"))
    locator_cache.init(block_processor.get_best_block_hash(), block_processor)
    assert len(locator_cache.blocks) == locator_cache.cache_size

    # Now let's fake a reorg of less than ``cache_size``. We'll go two blocks into the past.
    current_tip = block_processor.get_best_block_hash()
    current_tip_locators = locator_cache.blocks[current_tip]
    current_tip_parent = block_processor.get_block(current_tip).get("previousblockhash")
    current_tip_parent_locators = locator_cache.blocks[current_tip_parent]
    fake_tip = block_processor.get_block(current_tip_parent).get("previousblockhash")
    locator_cache.fix(fake_tip, block_processor)

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

    generate_blocks((config.get("LOCATOR_CACHE_SIZE") * 2))
    locator_cache.fix(block_processor.get_best_block_hash(), block_processor)

    # None of the data from the old cache is in the new cache
    for block_hash, locators in old_cache_blocks.items():
        assert block_hash not in locator_cache.blocks
        for locator in locators:
            assert locator not in locator_cache.cache

    # The data in the new cache corresponds to the last ``cache_size`` blocks.
    block_count = block_processor.get_block_count()
    for i in range(block_count, block_count - locator_cache.cache_size, -1):
        block_hash = bitcoin_cli.getblockhash(i)
        assert block_hash in locator_cache.blocks
        for locator in locator_cache.blocks[block_hash]:
            assert locator in locator_cache.cache


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


# FIXME: 194 will do with dummy appointment
def test_add_appointment_non_registered(watcher, generate_dummy_appointment):
    # Appointments from non-registered users should fail
    user_sk, user_pk = generate_keypair()

    appointment, dispute_tx = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    with pytest.raises(AuthenticationFailure, match="User not found"):
        watcher.add_appointment(appointment, appointment_signature)


# FIXME: 194 will do with dummy appointment
def test_add_appointment_no_slots(watcher, generate_dummy_appointment):
    # Appointments from register users with no available slots should aso fail
    user_sk, user_pk = generate_keypair()
    user_id = Cryptographer.get_compressed_pk(user_pk)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=0, subscription_expiry=10)

    appointment, dispute_tx = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    with pytest.raises(NotEnoughSlots):
        watcher.add_appointment(appointment, appointment_signature)


# FIXME: 194 will do with dummy appointment
def test_add_appointment(watcher, generate_dummy_appointment):
    # Simulate the user is registered
    user_sk, user_pk = generate_keypair()
    available_slots = 100
    user_id = Cryptographer.get_compressed_pk(user_pk)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=available_slots, subscription_expiry=10)

    appointment, dispute_tx = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    response = watcher.add_appointment(appointment, appointment_signature)
    assert response.get("locator") == appointment.locator
    assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
        Cryptographer.recover_pk(
            receipts.create_appointment_receipt(appointment_signature, response.get("start_block")),
            response.get("signature"),
        )
    )
    assert response.get("available_slots") == available_slots - 1

    # Check that we can also add an already added appointment (same locator)
    response = watcher.add_appointment(appointment, appointment_signature)
    assert response.get("locator") == appointment.locator
    assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
        Cryptographer.recover_pk(
            receipts.create_appointment_receipt(appointment_signature, response.get("start_block")),
            response.get("signature"),
        )
    )
    # The slot count should not have been reduced and only one copy is kept.
    assert response.get("available_slots") == available_slots - 1
    assert len(watcher.locator_uuid_map[appointment.locator]) == 1

    # If two appointments with the same locator come from different users, they are kept.
    another_user_sk, another_user_pk = generate_keypair()
    another_user_id = Cryptographer.get_compressed_pk(another_user_pk)
    watcher.gatekeeper.registered_users[another_user_id] = UserInfo(
        available_slots=available_slots, subscription_expiry=10
    )

    appointment_signature = Cryptographer.sign(appointment.serialize(), another_user_sk)
    response = watcher.add_appointment(appointment, appointment_signature)
    assert response.get("locator") == appointment.locator
    assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
        Cryptographer.recover_pk(
            receipts.create_appointment_receipt(appointment_signature, response.get("start_block")),
            response.get("signature"),
        )
    )
    assert response.get("available_slots") == available_slots - 1
    assert len(watcher.locator_uuid_map[appointment.locator]) == 2


def test_add_appointment_in_cache(watcher, generate_dummy_appointment):
    # Generate an appointment and add the dispute txid to the cache
    user_sk, user_pk = generate_keypair()
    user_id = Cryptographer.get_compressed_pk(user_pk)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=10)

    appointment, dispute_tx = generate_dummy_appointment()

    # Broadcast the transaction and add it manually to the Watcher cache (since the Watcher is not currently watching)
    generate_block_with_transactions(dispute_tx)
    dispute_txid = watcher.block_processor.decode_raw_transaction(dispute_tx).get("txid")
    watcher.locator_cache.cache[appointment.locator] = dispute_txid

    # Try to add the appointment
    user_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    response = watcher.add_appointment(appointment, user_signature)
    appointment_receipt = receipts.create_appointment_receipt(user_signature, response.get("start_block"))

    # The appointment is accepted but it's not in the Watcher
    assert (
        response
        and response.get("locator") == appointment.locator
        and Cryptographer.get_compressed_pk(watcher.signing_key.public_key)
        == Cryptographer.get_compressed_pk(Cryptographer.recover_pk(appointment_receipt, response.get("signature")))
    )
    assert not watcher.locator_uuid_map.get(appointment.locator)

    # It went to the Responder straightaway
    assert appointment.locator in [tracker.get("locator") for tracker in watcher.responder.trackers.values()]

    # Trying to send it again should fail since it is already in the Responder
    with pytest.raises(AppointmentAlreadyTriggered):
        watcher.add_appointment(appointment, Cryptographer.sign(appointment.serialize(), user_sk))


# FIXME: 194 will do with dummy appointment
def test_add_appointment_in_cache_invalid_blob(watcher):
    # Generate an appointment with an invalid transaction and add the dispute txid to the cache
    user_sk, user_pk = generate_keypair()
    user_id = Cryptographer.get_compressed_pk(user_pk)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=10)

    # We need to create the appointment manually
    commitment_tx, commitment_txid, penalty_tx = create_txs()

    locator = compute_locator(commitment_tx)
    dummy_appointment_data = {"tx": penalty_tx, "tx_id": commitment_txid, "to_self_delay": 20}
    encrypted_blob = Cryptographer.encrypt(penalty_tx[::-1], commitment_txid)

    appointment_data = {
        "locator": locator,
        "to_self_delay": dummy_appointment_data.get("to_self_delay"),
        "encrypted_blob": encrypted_blob,
        "user_id": get_random_value_hex(16),
    }

    appointment = Appointment.from_dict(appointment_data)
    watcher.locator_cache.cache[appointment.locator] = commitment_txid

    # Try to add the appointment
    user_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    response = watcher.add_appointment(appointment, user_signature)
    appointment_receipt = receipts.create_appointment_receipt(user_signature, response.get("start_block"))

    # The appointment is accepted but dropped (same as an invalid appointment that gets triggered)
    assert (
        response
        and response.get("locator") == appointment.locator
        and Cryptographer.get_compressed_pk(watcher.signing_key.public_key)
        == Cryptographer.get_compressed_pk(Cryptographer.recover_pk(appointment_receipt, response.get("signature")))
    )

    assert not watcher.locator_uuid_map.get(appointment.locator)
    assert appointment.locator not in [tracker.get("locator") for tracker in watcher.responder.trackers.values()]


def test_add_appointment_in_cache_invalid_transaction(watcher, generate_dummy_appointment):
    # Generate an appointment that cannot be decrypted and add the dispute txid to the cache
    user_sk, user_pk = generate_keypair()
    user_id = Cryptographer.get_compressed_pk(user_pk)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=1, subscription_expiry=10)

    appointment, dispute_tx = generate_dummy_appointment()
    appointment.encrypted_blob = appointment.encrypted_blob[::-1]
    dispute_txid = watcher.block_processor.decode_raw_transaction(dispute_tx).get("txid")
    watcher.locator_cache.cache[appointment.locator] = dispute_txid

    # Try to add the appointment
    user_signature = Cryptographer.sign(appointment.serialize(), user_sk)
    response = watcher.add_appointment(appointment, user_signature)
    appointment_receipt = receipts.create_appointment_receipt(user_signature, response.get("start_block"))

    # The appointment is accepted but dropped (same as an invalid appointment that gets triggered)
    assert (
        response
        and response.get("locator") == appointment.locator
        and Cryptographer.get_compressed_pk(watcher.signing_key.public_key)
        == Cryptographer.get_compressed_pk(Cryptographer.recover_pk(appointment_receipt, response.get("signature")))
    )

    assert not watcher.locator_uuid_map.get(appointment.locator)
    assert appointment.locator not in [tracker.get("locator") for tracker in watcher.responder.trackers.values()]


# FIXME: 194 will do with dummy appointment
def test_add_too_many_appointments(watcher, generate_dummy_appointment):
    # Simulate the user is registered
    user_sk, user_pk = generate_keypair()
    available_slots = 100
    user_id = Cryptographer.get_compressed_pk(user_pk)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=available_slots, subscription_expiry=10)

    # Appointments on top of the limit should be rejected
    watcher.appointments = dict()

    for i in range(MAX_APPOINTMENTS):
        appointment, dispute_tx = generate_dummy_appointment()
        appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
        response = watcher.add_appointment(appointment, appointment_signature)
        appointment_receipt = receipts.create_appointment_receipt(appointment_signature, response.get("start_block"))

        assert response.get("locator") == appointment.locator
        assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
            Cryptographer.recover_pk(appointment_receipt, response.get("signature"))
        )
        assert response.get("available_slots") == available_slots - (i + 1)

    with pytest.raises(AppointmentLimitReached):
        appointment, dispute_tx = generate_dummy_appointment()
        appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
        watcher.add_appointment(appointment, appointment_signature)


def test_do_watch(watcher, temp_db_manager, generate_dummy_appointment):
    watcher.db_manager = temp_db_manager

    # We will wipe all the previous data and add 5 appointments
    appointments, locator_uuid_map, dispute_txs = create_appointments(generate_dummy_appointment, APPOINTMENTS)

    # Set the data into the Watcher and in the db
    watcher.locator_uuid_map = locator_uuid_map
    watcher.appointments = {}
    watcher.gatekeeper.registered_users = {}

    # Simulate a register (times out in 10 bocks)
    user_id = get_random_value_hex(16)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(
        available_slots=100, subscription_expiry=watcher.block_processor.get_block_count() + 10
    )

    # Add the appointments
    for uuid, appointment in appointments.items():
        watcher.appointments[uuid] = {"locator": appointment.locator, "user_id": user_id}
        # Assume the appointment only takes one slot
        watcher.gatekeeper.registered_users[user_id].appointments[uuid] = 1
        watcher.db_manager.store_watcher_appointment(uuid, appointment.to_dict())
        watcher.db_manager.create_append_locator_map(appointment.locator, uuid)

    do_watch_thread = Thread(target=watcher.do_watch, daemon=True)
    do_watch_thread.start()

    # Broadcast the first two
    for dispute_tx in dispute_txs[:2]:
        bitcoin_cli.sendrawtransaction(dispute_tx)

    # After generating a block, the appointment count should have been reduced by 2 (two breaches)
    generate_blocks_with_delay(1)

    assert len(watcher.appointments) == APPOINTMENTS - 2

    # The rest of appointments will timeout after the subscription times-out (9 more blocks) + EXPIRY_DELTA
    # Wait for an additional block to be safe
    generate_blocks_with_delay(10 + config.get("EXPIRY_DELTA"))
    assert len(watcher.appointments) == 0

    # Check that they are not in the Gatekeeper either, only the two that passed to the Responder should remain
    assert len(watcher.gatekeeper.registered_users[user_id].appointments) == 2

    # FIXME: We should also add cases where the transactions are invalid. bitcoind_mock needs to be extended for this.


# TODO: depends on previous test
def test_do_watch_cache_update(watcher):
    # Test that data is properly added/remove to/from the cache

    for _ in range(10):
        blocks_in_cache = watcher.locator_cache.blocks
        oldest_block_hash = list(blocks_in_cache.keys())[0]
        oldest_block_data = blocks_in_cache.get(oldest_block_hash)
        rest_of_blocks = list(blocks_in_cache.keys())[1:]
        assert len(watcher.locator_cache.blocks) == watcher.locator_cache.cache_size

        generate_blocks_with_delay(1)

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


# FIXME: 194 will do with dummy watcher
def test_get_breaches(watcher, txids, locator_uuid_map):
    watcher.locator_uuid_map = locator_uuid_map
    locators_txid_map = {compute_locator(txid): txid for txid in txids}
    potential_breaches = watcher.get_breaches(locators_txid_map)

    # All the txids must breach
    assert locator_uuid_map.keys() == potential_breaches.keys()


# FIXME: 194 will do with dummy watcher
def test_get_breaches_random_data(watcher, locator_uuid_map):
    # The likelihood of finding a potential breach with random data should be negligible
    watcher.locator_uuid_map = locator_uuid_map
    txids = [get_random_value_hex(32) for _ in range(TEST_SET_SIZE)]
    locators_txid_map = {compute_locator(txid): txid for txid in txids}

    potential_breaches = watcher.get_breaches(locators_txid_map)

    # None of the txids should breach
    assert len(potential_breaches) == 0


# FIXME: 194 will do with dummy watcher and appointment
def test_check_breach(watcher, generate_dummy_appointment):
    # A breach will be flagged as valid only if the encrypted blob can be properly decrypted and the resulting data
    # matches a transaction format.
    uuid = uuid4().hex
    appointment, dispute_tx = generate_dummy_appointment()
    dispute_txid = watcher.block_processor.decode_raw_transaction(dispute_tx).get("txid")

    penalty_txid, penalty_rawtx = watcher.check_breach(uuid, appointment, dispute_txid)
    assert Cryptographer.encrypt(penalty_rawtx, dispute_txid) == appointment.encrypted_blob


# FIXME: 194 will do with dummy watcher and appointment
def test_check_breach_random_data(watcher, generate_dummy_appointment):
    # If a breach triggers an appointment with random data as encrypted blob, the check should fail.
    uuid = uuid4().hex
    appointment, dispute_tx = generate_dummy_appointment()
    dispute_txid = watcher.block_processor.decode_raw_transaction(dispute_tx).get("txid")

    # Set the blob to something "random"
    appointment.encrypted_blob = get_random_value_hex(200)

    with pytest.raises(EncryptionError):
        watcher.check_breach(uuid, appointment, dispute_txid)


# FIXME: 194 will do with dummy watcher and appointment
def test_check_breach_invalid_transaction(watcher, generate_dummy_appointment):
    # If the breach triggers an appointment with data that can be decrypted but does not match a transaction, it should
    # fail
    uuid = uuid4().hex
    appointment, dispute_tx = generate_dummy_appointment()
    dispute_txid = watcher.block_processor.decode_raw_transaction(dispute_tx).get("txid")

    # Set the blob to something "random"
    appointment.encrypted_blob = Cryptographer.encrypt(get_random_value_hex(200), dispute_txid)

    with pytest.raises(InvalidTransactionFormat):
        watcher.check_breach(uuid, appointment, dispute_txid)


# FIXME: 194 will do with dummy watcher
def test_filter_valid_breaches(watcher, generate_dummy_appointment):
    dispute_txid = "0437cd7f8525ceed2324359c2d0ba26006d92d856a9c20fa0241106ee5a597c9"
    encrypted_blob = (
        "a62aa9bb3c8591e4d5de10f1bd49db92432ce2341af55762cdc9242c08662f97f5f47da0a1aa88373508cd6e67e87eefddeca0cee98c1"
        "967ec1c1ecbb4c5e8bf08aa26159214e6c0bc4b2c7c247f87e7601d15c746fc4e711be95ba0e363001280138ba9a65b06c4aa6f592b21"
        "3635ee763984d522a4c225814510c8f7ab0801f36d4a68f5ee7dd3930710005074121a172c29beba79ed647ebaf7e7fab1bbd9a208251"
        "ef5486feadf2c46e33a7d66adf9dbbc5f67b55a34b1b3c4909dd34a482d759b0bc25ecd2400f656db509466d7479b5b92a2fadabccc9e"
        "c8918da8979a9feadea27531643210368fee494d3aaa4983e05d6cf082a49105e2f8a7c7821899239ba7dee12940acd7d8a629894b5d31"
        "e94b439cfe8d2e9f21e974ae5342a70c91e8"
    )

    dummy_appointment, _ = generate_dummy_appointment()
    dummy_appointment.encrypted_blob = encrypted_blob
    dummy_appointment.locator = compute_locator(dispute_txid)
    uuid = uuid4().hex

    appointments = {uuid: dummy_appointment}
    locator_uuid_map = {dummy_appointment.locator: [uuid]}
    breaches = {dummy_appointment.locator: dispute_txid}

    for uuid, appointment in appointments.items():
        watcher.appointments[uuid] = {"locator": appointment.locator, "user_id": appointment.user_id}
        watcher.db_manager.store_watcher_appointment(uuid, dummy_appointment.to_dict())
        watcher.db_manager.create_append_locator_map(dummy_appointment.locator, uuid)

    watcher.locator_uuid_map = locator_uuid_map

    valid_breaches, invalid_breaches = watcher.filter_breaches(breaches)

    # We have "triggered" a single breach and it was valid.
    assert len(invalid_breaches) == 0 and len(valid_breaches) == 1


# FIXME: 194 will do with dummy watcher and appointment
def test_filter_breaches_random_data(watcher, generate_dummy_appointment):
    appointments = {}
    locator_uuid_map = {}
    breaches = {}

    for i in range(TEST_SET_SIZE):
        dummy_appointment, _ = generate_dummy_appointment()
        uuid = uuid4().hex
        appointments[uuid] = {"locator": dummy_appointment.locator, "user_id": dummy_appointment.user_id}
        watcher.db_manager.store_watcher_appointment(uuid, dummy_appointment.to_dict())
        watcher.db_manager.create_append_locator_map(dummy_appointment.locator, uuid)

        locator_uuid_map[dummy_appointment.locator] = [uuid]

        if i % 2:
            dispute_txid = get_random_value_hex(32)
            breaches[dummy_appointment.locator] = dispute_txid

    watcher.locator_uuid_map = locator_uuid_map
    watcher.appointments = appointments

    valid_breaches, invalid_breaches = watcher.filter_breaches(breaches)

    # We have "triggered" TEST_SET_SIZE/2 breaches, all of them invalid.
    assert len(valid_breaches) == 0 and len(invalid_breaches) == TEST_SET_SIZE / 2
