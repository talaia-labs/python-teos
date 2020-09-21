import pytest
import random
from uuid import uuid4
from queue import Queue
from shutil import rmtree
from copy import deepcopy
from threading import Thread

from teos.carrier import Carrier
from teos.chain_monitor import ChainMonitor
from teos.block_processor import BlockProcessor
from teos.gatekeeper import Gatekeeper, UserInfo
from teos.appointments_dbm import AppointmentsDBM
from teos.responder import Responder, TransactionTracker, CONFIRMATIONS_BEFORE_RETRY

from common.constants import LOCATOR_LEN_HEX
from test.teos.conftest import (
    config,
    bitcoin_cli,
    generate_blocks,
    generate_blocks_with_delay,
    create_commitment_tx,
    generate_block_with_transactions,
)
from test.teos.unit.conftest import get_random_value_hex, bitcoind_feed_params


@pytest.fixture
def responder(db_manager, gatekeeper, carrier, block_processor):
    responder = Responder(db_manager, gatekeeper, carrier, block_processor)
    chain_monitor = ChainMonitor([Queue(), responder.block_queue], block_processor, bitcoind_feed_params)
    chain_monitor.monitor_chain()
    responder_thread = responder.awake()
    chain_monitor.activate()

    yield responder

    chain_monitor.terminate()
    responder_thread.join()


# FIXME: Check if this can be removed and used the general fixture
@pytest.fixture(scope="session")
def temp_db_manager():
    db_name = get_random_value_hex(8)
    db_manager = AppointmentsDBM(db_name)

    yield db_manager

    db_manager.db.close()
    rmtree(db_name)


def test_tracker_init():
    locator = get_random_value_hex(32)
    dispute_txid = get_random_value_hex(32)
    penalty_txid = get_random_value_hex(32)
    penalty_tx = get_random_value_hex(200)
    user_id = get_random_value_hex(16)

    tracker = TransactionTracker(locator, dispute_txid, penalty_txid, penalty_tx, user_id)

    assert (
        tracker.locator == locator
        and tracker.dispute_txid == dispute_txid
        and tracker.penalty_txid == penalty_txid
        and tracker.penalty_rawtx == penalty_tx
        and tracker.user_id == user_id
    )


# FIXME: 194 will do with dummy tracker
def test_tracker_to_dict(generate_dummy_tracker):
    tracker = generate_dummy_tracker()
    tracker_dict = tracker.to_dict()

    assert (
        tracker.locator == tracker_dict["locator"]
        and tracker.dispute_txid == tracker_dict["dispute_txid"]
        and tracker.penalty_txid == tracker_dict["penalty_txid"]
        and tracker.penalty_rawtx == tracker_dict["penalty_rawtx"]
        and tracker.user_id == tracker_dict["user_id"]
    )


# FIXME: 194 will do with dummy tracker
def test_tracker_from_dict(generate_dummy_tracker):
    tracker_dict = generate_dummy_tracker().to_dict()
    new_tracker = TransactionTracker.from_dict(tracker_dict)

    assert tracker_dict == new_tracker.to_dict()


# FIXME: 194 will do with dummy tracker
def test_tracker_from_dict_invalid_data(generate_dummy_tracker):
    tracker_dict = generate_dummy_tracker().to_dict()

    for value in ["locator", "dispute_txid", "penalty_txid", "penalty_rawtx", "user_id"]:
        tracker_dict_copy = deepcopy(tracker_dict)
        tracker_dict_copy[value] = None

        with pytest.raises(ValueError):
            TransactionTracker.from_dict(tracker_dict_copy)


# FIXME: 194 will do with dummy tracker
def test_tracker_get_summary(generate_dummy_tracker):
    tracker = generate_dummy_tracker()
    assert tracker.get_summary() == {
        "locator": tracker.locator,
        "user_id": tracker.user_id,
        "penalty_txid": tracker.penalty_txid,
    }


def test_init_responder(temp_db_manager, gatekeeper, carrier, block_processor, responder):
    assert isinstance(responder.trackers, dict) and len(responder.trackers) == 0
    assert isinstance(responder.tx_tracker_map, dict) and len(responder.tx_tracker_map) == 0
    assert isinstance(responder.unconfirmed_txs, list) and len(responder.unconfirmed_txs) == 0
    assert isinstance(responder.missed_confirmations, dict) and len(responder.missed_confirmations) == 0
    assert isinstance(responder.block_queue, Queue) and responder.block_queue.empty()
    assert isinstance(responder.db_manager, AppointmentsDBM)
    assert isinstance(responder.gatekeeper, Gatekeeper)
    assert isinstance(responder.carrier, Carrier)
    assert isinstance(responder.block_processor, BlockProcessor)
    assert responder.last_known_block is None or isinstance(responder.last_known_block, str)


def test_on_sync(responder, block_processor):
    # We're on sync if we're 1 or less blocks behind the tip
    chain_tip = block_processor.get_best_block_hash()
    assert responder.on_sync(chain_tip) is True

    generate_blocks(1)
    assert responder.on_sync(chain_tip) is True


def test_on_sync_fail(responder, block_processor):
    # This should fail if we're more than 1 block behind the tip
    chain_tip = block_processor.get_best_block_hash()
    generate_blocks(2)

    assert responder.on_sync(chain_tip) is False


def test_handle_breach(db_manager, gatekeeper, carrier, responder, block_processor, generate_dummy_tracker):
    uuid = uuid4().hex
    commitment_tx = create_commitment_tx()
    tracker = generate_dummy_tracker(commitment_tx)
    generate_block_with_transactions(commitment_tx)

    # The block_hash passed to add_response does not matter much now. It will in the future to deal with errors
    receipt = responder.handle_breach(
        tracker.locator,
        uuid,
        tracker.dispute_txid,
        tracker.penalty_txid,
        tracker.penalty_rawtx,
        tracker.user_id,
        block_hash=get_random_value_hex(32),
    )

    assert receipt.delivered is True


def test_handle_breach_bad_response(
    db_manager, gatekeeper, carrier, responder, block_processor, generate_dummy_tracker
):
    # We need a new carrier here, otherwise the transaction will be flagged as previously sent and receipt.delivered
    # will be True

    uuid = uuid4().hex
    commitment_tx = create_commitment_tx()
    tracker = generate_dummy_tracker(commitment_tx)

    # The block_hash passed to add_response does not matter much now. It will in the future to deal with errors
    receipt = responder.handle_breach(
        tracker.locator,
        uuid,
        tracker.dispute_txid,
        tracker.penalty_txid,
        tracker.penalty_rawtx,
        tracker.user_id,
        block_hash=get_random_value_hex(32),
    )

    # Notice we are not minting a block with the commitment transaction, so broadcasting the penalty will fail
    assert receipt.delivered is False


# FIXME: 194 will do with dummy tracker
def test_add_tracker(responder, generate_dummy_tracker):
    for _ in range(20):
        uuid = uuid4().hex
        confirmations = 0
        tracker = generate_dummy_tracker()

        # Check the tracker is not within the responder trackers before adding it
        assert uuid not in responder.trackers
        assert tracker.penalty_txid not in responder.tx_tracker_map
        assert tracker.penalty_txid not in responder.unconfirmed_txs

        responder.add_tracker(
            uuid,
            tracker.locator,
            tracker.dispute_txid,
            tracker.penalty_txid,
            tracker.penalty_rawtx,
            tracker.user_id,
            confirmations,
        )

        # Check the tracker is within the responder after add_tracker
        assert uuid in responder.trackers
        assert tracker.penalty_txid in responder.tx_tracker_map
        assert tracker.penalty_txid in responder.unconfirmed_txs

        # Check that the rest of tracker data also matches
        assert (
            responder.trackers[uuid].get("penalty_txid") == tracker.penalty_txid
            and responder.trackers[uuid].get("locator") == tracker.locator
            and responder.trackers[uuid].get("user_id") == tracker.user_id
        )


# FIXME: 194 will do with dummy tracker
def test_add_tracker_same_penalty_txid(responder, generate_dummy_tracker):
    # Test that multiple trackers with the same penalty can be added
    confirmations = 0
    tracker = generate_dummy_tracker()
    uuid_1 = uuid4().hex
    uuid_2 = uuid4().hex

    responder.add_tracker(
        uuid_1,
        tracker.locator,
        tracker.dispute_txid,
        tracker.penalty_txid,
        tracker.penalty_rawtx,
        tracker.user_id,
        confirmations,
    )
    responder.add_tracker(
        uuid_2,
        tracker.locator,
        tracker.dispute_txid,
        tracker.penalty_txid,
        tracker.penalty_rawtx,
        tracker.user_id,
        confirmations,
    )

    # Check that both trackers have been added
    assert uuid_1 in responder.trackers and uuid_2 in responder.trackers
    assert tracker.penalty_txid in responder.tx_tracker_map
    assert tracker.penalty_txid in responder.unconfirmed_txs

    # Check that the rest of tracker data also matches
    for uuid in [uuid_1, uuid_2]:
        assert (
            responder.trackers[uuid].get("penalty_txid") == tracker.penalty_txid
            and responder.trackers[uuid].get("locator") == tracker.locator
            and responder.trackers[uuid].get("user_id") == tracker.user_id
        )


# FIXME: 194 will do with dummy tracker
def test_add_tracker_already_confirmed(responder, generate_dummy_tracker):
    # Tests that a tracker of an already confirmed penalty can be added
    for i in range(20):
        uuid = uuid4().hex
        confirmations = i + 1
        tracker = generate_dummy_tracker()

        responder.add_tracker(
            uuid,
            tracker.locator,
            tracker.dispute_txid,
            tracker.penalty_txid,
            tracker.penalty_rawtx,
            tracker.user_id,
            confirmations,
        )

        assert tracker.penalty_txid not in responder.unconfirmed_txs
        assert (
            responder.trackers[uuid].get("penalty_txid") == tracker.penalty_txid
            and responder.trackers[uuid].get("locator") == tracker.locator
            and responder.trackers[uuid].get("user_id") == tracker.user_id
        )


def test_do_watch(temp_db_manager, gatekeeper, carrier, block_processor, generate_dummy_tracker):
    commitment_txs = [create_commitment_tx() for _ in range(20)]
    trackers = [generate_dummy_tracker(commitment_tx) for commitment_tx in commitment_txs]
    subscription_expiry = block_processor.get_block_count() + 110

    # Broadcast all commitment transactions
    generate_block_with_transactions(commitment_txs)

    # Create a fresh responder to simplify the test
    responder = Responder(temp_db_manager, gatekeeper, carrier, block_processor)
    chain_monitor = ChainMonitor([Queue(), responder.block_queue], block_processor, bitcoind_feed_params)
    chain_monitor.monitor_chain()
    chain_monitor.activate()

    # Let's set up the trackers first
    for tracker in trackers:
        uuid = uuid4().hex

        # Simulate user registration so trackers can properly expire
        responder.gatekeeper.registered_users[tracker.user_id] = UserInfo(
            available_slots=10, subscription_expiry=subscription_expiry
        )

        # Add data to the Responder
        responder.trackers[uuid] = tracker.get_summary()
        responder.tx_tracker_map[tracker.penalty_txid] = [uuid]
        responder.missed_confirmations[tracker.penalty_txid] = 0
        responder.unconfirmed_txs.append(tracker.penalty_txid)
        # Assuming the appointment only took a single slot
        responder.gatekeeper.registered_users[tracker.user_id].appointments[uuid] = 1

        # We also need to store the info in the db
        responder.db_manager.create_triggered_appointment_flag(uuid)
        responder.db_manager.store_responder_tracker(uuid, tracker.to_dict())

    # Let's start to watch
    Thread(target=responder.do_watch, daemon=True).start()

    # And broadcast some of the penalties
    broadcast_txs = []
    for tracker in trackers[:5]:
        bitcoin_cli.sendrawtransaction(tracker.penalty_rawtx)
        broadcast_txs.append(tracker.penalty_txid)

    # Mine a block
    generate_blocks_with_delay(1)

    # The transactions we sent shouldn't be in the unconfirmed transaction list anymore
    assert not set(broadcast_txs).issubset(responder.unconfirmed_txs)

    # CONFIRMATIONS_BEFORE_RETRY+1 blocks after, the responder should rebroadcast the unconfirmed txs (15 remaining)
    generate_blocks_with_delay(CONFIRMATIONS_BEFORE_RETRY + 1)
    assert len(responder.unconfirmed_txs) == 0
    assert len(responder.trackers) == 20

    # Generating 100 - CONFIRMATIONS_BEFORE_RETRY -2 additional blocks should complete the first 5 trackers
    generate_blocks_with_delay(100 - CONFIRMATIONS_BEFORE_RETRY - 2)
    assert len(responder.unconfirmed_txs) == 0
    assert len(responder.trackers) == 15
    # Check they are not in the Gatekeeper either
    for tracker in trackers[:5]:
        assert len(responder.gatekeeper.registered_users[tracker.user_id].appointments) == 0

    # CONFIRMATIONS_BEFORE_RETRY additional blocks should complete the rest
    generate_blocks_with_delay(CONFIRMATIONS_BEFORE_RETRY)
    assert len(responder.unconfirmed_txs) == 0
    assert len(responder.trackers) == 0
    # Check they are not in the Gatekeeper either
    for tracker in trackers[5:]:
        assert len(responder.gatekeeper.registered_users[tracker.user_id].appointments) == 0


def test_check_confirmations(db_manager, gatekeeper, carrier, responder, block_processor):
    # check_confirmations checks, given a list of transaction for a block, what of the known penalty transaction have
    # been confirmed. To test this we need to create a list of transactions and the state of the Responder
    txs = [get_random_value_hex(32) for _ in range(20)]

    # The responder has a list of unconfirmed transaction, let make that some of them are the ones we've received
    responder.unconfirmed_txs = [get_random_value_hex(32) for _ in range(10)]
    txs_subset = random.sample(txs, k=10)
    responder.unconfirmed_txs.extend(txs_subset)

    # We also need to add them to the tx_tracker_map since they would be there in normal conditions
    responder.tx_tracker_map = {
        txid: TransactionTracker(txid[:LOCATOR_LEN_HEX], txid, None, None, None) for txid in responder.unconfirmed_txs
    }

    # Let's make sure that there are no txs with missed confirmations yet
    assert len(responder.missed_confirmations) == 0

    responder.check_confirmations(txs)

    # After checking confirmations the txs in txs_subset should be confirmed (not part of unconfirmed_txs anymore)
    # and the rest should have a missing confirmation
    for tx in txs_subset:
        assert tx not in responder.unconfirmed_txs

    for tx in responder.unconfirmed_txs:
        assert responder.missed_confirmations[tx] == 1


def test_get_txs_to_rebroadcast(responder):
    # Let's create a few fake txids and assign at least 6 missing confirmations to each
    txs_missing_too_many_conf = {get_random_value_hex(32): 6 + i for i in range(10)}

    # Let's create some other transaction that has missed some confirmations but not that many
    txs_missing_some_conf = {get_random_value_hex(32): 3 for _ in range(10)}

    # All the txs in the first dict should be flagged as to_rebroadcast
    responder.missed_confirmations = txs_missing_too_many_conf
    txs_to_rebroadcast = responder.get_txs_to_rebroadcast()
    assert txs_to_rebroadcast == list(txs_missing_too_many_conf.keys())

    # Non of the txs in the second dict should be flagged
    responder.missed_confirmations = txs_missing_some_conf
    txs_to_rebroadcast = responder.get_txs_to_rebroadcast()
    assert txs_to_rebroadcast == []

    # Let's check that it also works with a mixed dict
    responder.missed_confirmations.update(txs_missing_too_many_conf)
    txs_to_rebroadcast = responder.get_txs_to_rebroadcast()
    assert txs_to_rebroadcast == list(txs_missing_too_many_conf.keys())


def test_get_completed_trackers(db_manager, gatekeeper, carrier, responder, block_processor, generate_dummy_tracker):
    commitment_txs = [create_commitment_tx() for _ in range(30)]
    generate_block_with_transactions(commitment_txs)
    # A complete tracker is a tracker whose penalty transaction has been irrevocably resolved (i.e. has reached 100
    # confirmations)
    # We'll create 3 type of txs: irrevocably resolved, confirmed but not irrevocably resolved, and unconfirmed
    trackers_ir_resolved = {uuid4().hex: generate_dummy_tracker(commitment_tx) for commitment_tx in commitment_txs[:10]}

    trackers_confirmed = {uuid4().hex: generate_dummy_tracker(commitment_tx) for commitment_tx in commitment_txs[10:20]}

    trackers_unconfirmed = {}
    for commitment_tx in commitment_txs[20:]:
        tracker = generate_dummy_tracker(commitment_tx)
        responder.unconfirmed_txs.append(tracker.penalty_txid)
        trackers_unconfirmed[uuid4().hex] = tracker

    all_trackers = {}
    all_trackers.update(trackers_ir_resolved)
    all_trackers.update(trackers_confirmed)
    all_trackers.update(trackers_unconfirmed)

    # Let's add all to the Responder
    for uuid, tracker in all_trackers.items():
        responder.trackers[uuid] = tracker.get_summary()

    for uuid, tracker in trackers_ir_resolved.items():
        bitcoin_cli.sendrawtransaction(tracker.penalty_rawtx)

    generate_blocks_with_delay(1)

    for uuid, tracker in trackers_confirmed.items():
        bitcoin_cli.sendrawtransaction(tracker.penalty_rawtx)

    # ir_resolved have 100 confirmations and confirmed have 99
    generate_blocks_with_delay(99)

    # Let's check
    completed_trackers = responder.get_completed_trackers()
    ended_trackers_keys = list(trackers_ir_resolved.keys())
    assert set(completed_trackers) == set(ended_trackers_keys)

    # Generating 1 additional blocks should also include confirmed
    generate_blocks_with_delay(1)

    completed_trackers = responder.get_completed_trackers()
    ended_trackers_keys.extend(list(trackers_confirmed.keys()))
    assert set(completed_trackers) == set(ended_trackers_keys)


def test_get_outdated_trackers(responder, generate_dummy_tracker):
    # Expired trackers are those whose subscription has reached the expiry block and have not been confirmed.
    # Confirmed trackers that have reached their expiry will be kept until completed
    current_block = responder.block_processor.get_block_count()

    # Let's first register a couple of users
    user1_id = get_random_value_hex(16)
    responder.gatekeeper.registered_users[user1_id] = UserInfo(
        available_slots=10, subscription_expiry=current_block + 15
    )
    user2_id = get_random_value_hex(16)
    responder.gatekeeper.registered_users[user2_id] = UserInfo(
        available_slots=10, subscription_expiry=current_block + 16
    )

    # And create some trackers and add them to the corresponding user in the Gatekeeper
    outdated_unconfirmed_trackers_15 = {}
    outdated_unconfirmed_trackers_16 = {}
    outdated_confirmed_trackers_15 = {}
    for _ in range(10):
        uuid = uuid4().hex
        dummy_tracker = generate_dummy_tracker()
        dummy_tracker.user_id = user1_id
        outdated_unconfirmed_trackers_15[uuid] = dummy_tracker
        responder.unconfirmed_txs.append(dummy_tracker.penalty_txid)
        # Assume the appointment only took a single slot
        responder.gatekeeper.registered_users[dummy_tracker.user_id].appointments[uuid] = 1

    for _ in range(10):
        uuid = uuid4().hex
        dummy_tracker = generate_dummy_tracker()
        dummy_tracker.user_id = user1_id
        outdated_confirmed_trackers_15[uuid] = dummy_tracker
        # Assume the appointment only took a single slot
        responder.gatekeeper.registered_users[dummy_tracker.user_id].appointments[uuid] = 1

    for _ in range(10):
        uuid = uuid4().hex
        dummy_tracker = generate_dummy_tracker()
        dummy_tracker.user_id = user2_id
        outdated_unconfirmed_trackers_16[uuid] = dummy_tracker
        responder.unconfirmed_txs.append(dummy_tracker.penalty_txid)
        # Assume the appointment only took a single slot
        responder.gatekeeper.registered_users[dummy_tracker.user_id].appointments[uuid] = 1

    all_trackers = {}
    all_trackers.update(outdated_confirmed_trackers_15)
    all_trackers.update(outdated_unconfirmed_trackers_15)
    all_trackers.update(outdated_unconfirmed_trackers_16)

    # Add everything to the Responder
    for uuid, tracker in all_trackers.items():
        responder.trackers[uuid] = tracker.get_summary()

    # Currently nothing should be outdated
    assert responder.get_outdated_trackers(current_block) == []

    # 15 blocks (+ EXPIRY_DELTA) afterwards only user1's confirmed trackers should be outdated
    assert responder.get_outdated_trackers(current_block + 15 + config.get("EXPIRY_DELTA")) == list(
        outdated_unconfirmed_trackers_15.keys()
    )

    # 1 (+ EXPIRY_DELTA) block after that user2's should be outdated
    assert responder.get_outdated_trackers(current_block + 16 + config.get("EXPIRY_DELTA")) == list(
        outdated_unconfirmed_trackers_16.keys()
    )


def test_rebroadcast(db_manager, gatekeeper, carrier, responder, block_processor, generate_dummy_tracker):
    # Include the commitment txs in a block
    commitment_txs = [create_commitment_tx() for _ in range(20)]
    generate_block_with_transactions(commitment_txs)
    txs_to_rebroadcast = []

    # Rebroadcast calls add_response with retry=True. The tracker data is already in trackers.
    for i, commitment_tx in enumerate(commitment_txs):
        uuid = uuid4().hex
        tracker = generate_dummy_tracker(commitment_tx)

        responder.trackers[uuid] = {
            "locator": tracker.locator,
            "penalty_txid": tracker.penalty_txid,
            "user_id": tracker.user_id,
        }

        # We need to add it to the db too
        responder.db_manager.create_triggered_appointment_flag(uuid)
        responder.db_manager.store_responder_tracker(uuid, tracker.to_dict())

        responder.tx_tracker_map[tracker.penalty_txid] = [uuid]
        responder.unconfirmed_txs.append(tracker.penalty_txid)

        # Let's add some of the txs in the rebroadcast list
        if (i % 2) == 0:
            txs_to_rebroadcast.append(tracker.penalty_txid)

    # The block_hash passed to rebroadcast does not matter much now. It will in the future to deal with errors
    receipts = responder.rebroadcast(txs_to_rebroadcast)

    # All txs should have been delivered and the missed confirmation reset
    for txid, receipt in receipts:
        # Sanity check
        assert txid in txs_to_rebroadcast

        assert receipt.delivered is True
        assert responder.missed_confirmations[txid] == 0
