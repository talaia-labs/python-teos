import time
import pytest
import random
from uuid import uuid4
from queue import Queue
from copy import deepcopy
from threading import Thread

from teos.gatekeeper import UserInfo, Gatekeeper as RealGatekeeper
from teos.responder import Responder, TransactionTracker, CONFIRMATIONS_BEFORE_RETRY

from common.constants import LOCATOR_LEN_HEX

from test.teos.unit.mocks import AppointmentsDBM, Gatekeeper, Carrier, BlockProcessor
from test.teos.conftest import (
    config,
    mock_generate_blocks,
    generate_blocks_with_delay,
)
from test.teos.unit.conftest import (
    get_random_value_hex,
    run_test_blocking_command_bitcoind_crash,
)
from test.teos.unit.test_watcher import mock_receipt_true, mock_receipt_false


@pytest.fixture
def responder(dbm_mock, gatekeeper_mock, carrier_mock, block_processor_mock):
    responder = Responder(dbm_mock, gatekeeper_mock, carrier_mock, block_processor_mock)

    return responder


def test_tracker_init():
    # Simple test to check that creating a Tracker works
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


def test_tracker_to_dict(generate_dummy_tracker):
    # Check that the tracker can be converted into a dictionary
    tracker = generate_dummy_tracker()
    tracker_dict = tracker.to_dict()

    assert (
        tracker.locator == tracker_dict["locator"]
        and tracker.dispute_txid == tracker_dict["dispute_txid"]
        and tracker.penalty_txid == tracker_dict["penalty_txid"]
        and tracker.penalty_rawtx == tracker_dict["penalty_rawtx"]
        and tracker.user_id == tracker_dict["user_id"]
    )


def test_tracker_from_dict(generate_dummy_tracker):
    # Check that a tracker can be created from a dictionary
    tracker_dict = generate_dummy_tracker().to_dict()
    new_tracker = TransactionTracker.from_dict(tracker_dict)

    assert tracker_dict == new_tracker.to_dict()


def test_tracker_from_dict_invalid_data(generate_dummy_tracker):
    # If the provided dict data is invalid, the Tracker creation will fail
    tracker_dict = generate_dummy_tracker().to_dict()

    for value in ["locator", "dispute_txid", "penalty_txid", "penalty_rawtx", "user_id"]:
        tracker_dict_copy = deepcopy(tracker_dict)
        tracker_dict_copy[value] = None

        with pytest.raises(ValueError):
            TransactionTracker.from_dict(tracker_dict_copy)


def test_tracker_get_summary(generate_dummy_tracker):
    # Check that the summary of the tracker can be created from valid data
    tracker = generate_dummy_tracker()
    assert tracker.get_summary() == {
        "locator": tracker.locator,
        "user_id": tracker.user_id,
        "penalty_txid": tracker.penalty_txid,
    }


def test_init_responder(responder):
    # Test that the Responder init set the proper parameters in place. We use mocks for the other components but it
    # shouldn't matter
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


def test_on_sync(responder, monkeypatch):
    # We're on sync if we're, at most, 1 block behind the tip
    chain_tip = get_random_value_hex(32)

    monkeypatch.setattr(responder.block_processor, "get_distance_to_tip", lambda x, blocking: 0)
    assert responder.on_sync(chain_tip) is True
    monkeypatch.setattr(responder.block_processor, "get_distance_to_tip", lambda x, blocking: 1)
    assert responder.on_sync(chain_tip) is True

    # Otherwise we are off sync
    monkeypatch.setattr(responder.block_processor, "get_distance_to_tip", lambda x, blocking: 2)
    assert responder.on_sync(chain_tip) is False


def test_handle_breach(responder, generate_dummy_tracker, monkeypatch):
    tracker = generate_dummy_tracker()

    # Mock the interaction with the Carrier. We're simulating the tx going  through, meaning the commitment is already
    # in the chain
    monkeypatch.setattr(responder.carrier, "send_transaction", mock_receipt_true)

    # Check the breach
    receipt = responder.handle_breach(
        tracker.locator,
        uuid4().hex,
        tracker.dispute_txid,
        tracker.penalty_txid,
        tracker.penalty_rawtx,
        tracker.user_id,
        block_hash=get_random_value_hex(32),
    )
    assert receipt.delivered is True


def test_handle_breach_bad_response(responder, generate_dummy_tracker, monkeypatch):
    tracker = generate_dummy_tracker()

    # Mock the interaction with the Carrier. We're simulating the tx NOT going through, meaning the commitment is not
    # in the chain
    monkeypatch.setattr(responder.carrier, "send_transaction", mock_receipt_false)

    # Check a breach without the commitment being known
    receipt = responder.handle_breach(
        tracker.locator,
        uuid4().hex,
        tracker.dispute_txid,
        tracker.penalty_txid,
        tracker.penalty_rawtx,
        tracker.user_id,
        block_hash=get_random_value_hex(32),
    )

    # The penalty should be therefore rejected
    assert receipt.delivered is False


def test_add_tracker(responder, generate_dummy_tracker):
    # Test adding trackers to the Responder. Notice that adding trackers is guarded by handle_breach, meaning that, for
    # the sake of the test, we can add data assuming it has already been checked.
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


def test_add_tracker_same_penalty_txid(responder, generate_dummy_tracker):
    # Test that multiple trackers with the same penalty can be added
    confirmations = 0
    tracker = generate_dummy_tracker()
    uuid_1 = uuid4().hex
    uuid_2 = uuid4().hex

    for uuid in [uuid_1, uuid_2]:
        responder.add_tracker(
            uuid,
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

        # In this case the tracker won't be added to the unconfirmed transactions list
        assert tracker.penalty_txid not in responder.unconfirmed_txs
        assert (
            responder.trackers[uuid].get("penalty_txid") == tracker.penalty_txid
            and responder.trackers[uuid].get("locator") == tracker.locator
            and responder.trackers[uuid].get("user_id") == tracker.user_id
        )


def test_do_watch(responder, user_dbm_mock, generate_dummy_tracker, monkeypatch):
    # We need a real Gatekeeper to check that the data is properly deleted when necessary
    responder.gatekeeper = RealGatekeeper(
        user_dbm_mock,
        responder.block_processor,
        config.get("SUBSCRIPTION_SLOTS"),
        config.get("SUBSCRIPTION_DURATION"),
        config.get("EXPIRY_DELTA"),
    )

    trackers_uuids = [uuid4().hex for _ in range(20)]
    trackers = [generate_dummy_tracker() for _ in range(20)]

    # Add the trackers to the Responder and to the Watchers database (so we can check for deletion later on)
    for uuid, tracker in zip(trackers_uuids, trackers):
        responder.add_tracker(
            uuid, tracker.locator, tracker.dispute_txid, tracker.penalty_txid, tracker.penalty_rawtx, tracker.user_id,
        )

        # This is stored just to check for deletion once the Tracker is completed
        responder.db_manager.create_triggered_appointment_flag(uuid)
        responder.db_manager.store_watcher_appointment(uuid, tracker.to_dict())

    # Add the data to the Gatekeeper too so we can check it being deleted when it's due
    for uuid, tracker in zip(trackers_uuids, trackers):
        if tracker.user_id in responder.gatekeeper.registered_users:
            responder.gatekeeper.registered_users[tracker.user_id].appointments[uuid] = 1
        else:
            responder.gatekeeper.registered_users[tracker.user_id] = UserInfo(100, 1000, {uuid: 1})

    # Let's start to watch
    blocks = {}
    do_watch_thread = Thread(target=responder.do_watch, daemon=True)
    do_watch_thread.start()
    time.sleep(1)

    # Mock the Gatekeeper, the Carrier and the penalties as broadcast
    broadcast_txs = [tracker.penalty_txid for tracker in trackers[:5]]
    rest_txs = [tracker.penalty_txid for tracker in trackers[5:]]
    monkeypatch.setattr(responder.gatekeeper, "get_outdated_appointments", lambda x: [])
    next_block = {
        "tx": broadcast_txs,
        "previousblockhash": responder.last_known_block,
        "height": 1,
        "hash": get_random_value_hex(32),
    }
    monkeypatch.setattr(
        responder.block_processor, "get_block", lambda x, blocking: next_block,
    )

    # Mock a new block and check
    mock_generate_blocks(1, blocks, responder.block_queue)

    # The transactions we sent shouldn't be in the unconfirmed transaction list anymore
    assert not set(broadcast_txs).issubset(responder.unconfirmed_txs)

    # CONFIRMATIONS_BEFORE_RETRY-1 blocks after, the responder should rebroadcast the unconfirmed txs (15 remaining)
    monkeypatch.setattr(
        responder.block_processor, "get_block", lambda x, blocking: blocks.get(x),
    )
    monkeypatch.setattr(responder.carrier, "send_transaction", mock_receipt_true)
    mock_generate_blocks(
        CONFIRMATIONS_BEFORE_RETRY - 1, blocks, responder.block_queue, prev_block_hash=responder.last_known_block
    )
    # Check that the transactions have been just rebroadcast
    for _, conf in responder.missed_confirmations.items():
        assert conf == 0

    #  Add one more block containing the unconfirmed transactions that were just broadcast
    mock_generate_blocks(1, blocks, responder.block_queue, prev_block_hash=responder.last_known_block, txs=rest_txs)
    assert len(responder.unconfirmed_txs) == 0
    assert len(responder.trackers) == 20

    # Generating 100 - CONFIRMATIONS_BEFORE_RETRY -2 additional blocks should complete the first 5 trackers
    # This can be simulated mocking Responder.get_completed_trackers
    monkeypatch.setattr(responder, "get_completed_trackers", lambda: trackers_uuids[:5])
    # Generate a block to force the update
    mock_generate_blocks(1, blocks, responder.block_queue, prev_block_hash=responder.last_known_block)

    # The trackers are not in memory anymore nor the database
    assert len(responder.unconfirmed_txs) == 0
    assert len(responder.trackers) == 15
    # Check they are not in the Gatekeeper either
    for tracker in trackers[:5]:
        assert len(responder.gatekeeper.registered_users[tracker.user_id].appointments) == 0

    # And they have been removed from the database too (both Responder's and Watcher's)
    db_trackers = responder.db_manager.load_responder_trackers()
    assert not set(trackers_uuids[:5]).issubset(list(db_trackers.keys()))
    assert set(trackers_uuids[5:]).issubset(list(db_trackers.keys()))

    watcher_flags = responder.db_manager.load_all_triggered_flags()
    assert not set(trackers_uuids[:5]).issubset(watcher_flags)
    assert set(trackers_uuids[5:]).issubset(watcher_flags)
    db_appointments = responder.db_manager.load_watcher_appointments(include_triggered=True)
    assert not set(trackers_uuids[:5]).issubset(db_appointments)
    assert set(trackers_uuids[5:]).issubset(db_appointments)

    # CONFIRMATIONS_BEFORE_RETRY additional blocks should complete the rest
    monkeypatch.setattr(responder, "get_completed_trackers", lambda: trackers_uuids[5:])
    # Generate a block to force the update
    mock_generate_blocks(1, blocks, responder.block_queue, prev_block_hash=responder.last_known_block)

    assert len(responder.unconfirmed_txs) == 0
    assert len(responder.trackers) == 0
    # Check they are not in the Gatekeeper either
    for tracker in trackers[5:]:
        assert len(responder.gatekeeper.registered_users[tracker.user_id].appointments) == 0

    # The data is not in the database either
    assert len(responder.db_manager.load_responder_trackers()) == 0
    assert len(responder.db_manager.load_watcher_appointments()) == 0
    assert len(responder.db_manager.load_all_triggered_flags()) == 0


def test_check_confirmations(responder, monkeypatch):
    # check_confirmations checks, given a list of transaction for a block, what of the known penalty transaction have
    # been confirmed. To test this we need to create a list of transactions and the state of the Responder

    # The responder has a list of unconfirmed transaction, let make that some of them are the ones we've received
    txs = [get_random_value_hex(32) for _ in range(20)]
    unconfirmed_txs = [get_random_value_hex(32) for _ in range(10)]
    txs_subset = random.sample(txs, k=10)
    unconfirmed_txs.extend(txs_subset)

    # We also need to add them to the tx_tracker_map since they would be there in normal conditions
    tx_tracker_map = {
        txid: TransactionTracker(txid[:LOCATOR_LEN_HEX], txid, None, None, None) for txid in unconfirmed_txs
    }

    # Mock the structures
    monkeypatch.setattr(responder, "unconfirmed_txs", unconfirmed_txs)
    monkeypatch.setattr(responder, "tx_tracker_map", tx_tracker_map)

    # Let's make sure that there are no txs with missed confirmations yet
    assert len(responder.missed_confirmations) == 0

    # After checking confirmations the txs in txs_subset should be confirmed (not part of unconfirmed_txs anymore)
    # and the rest should have a missing confirmation
    responder.check_confirmations(txs)

    for tx in txs_subset:
        assert tx not in responder.unconfirmed_txs

    for tx in responder.unconfirmed_txs:
        assert responder.missed_confirmations[tx] == 1


def test_get_txs_to_rebroadcast(responder, monkeypatch):
    # Transactions are flagged to be rebroadcast once they've missed 6 confirmations.
    # Let's create a few fake txids and assign at least 6 missing confirmations to each
    txs_missing_too_many_conf = {get_random_value_hex(32): 6 + i for i in range(10)}

    # Let's create some other transaction that has missed some confirmations but not that many
    txs_missing_some_conf = {get_random_value_hex(32): 3 for _ in range(10)}

    # All the txs in the first dict should be flagged as to_rebroadcast
    monkeypatch.setattr(responder, "missed_confirmations", txs_missing_too_many_conf)

    txs_to_rebroadcast = responder.get_txs_to_rebroadcast()
    assert txs_to_rebroadcast == list(txs_missing_too_many_conf.keys())

    # Non of the txs in the second dict should be flagged
    monkeypatch.setattr(responder, "missed_confirmations", txs_missing_some_conf)
    txs_to_rebroadcast = responder.get_txs_to_rebroadcast()
    assert txs_to_rebroadcast == []

    # Let's check that it also works with a mixed dict
    txs_missing_some_conf.update(txs_missing_too_many_conf)
    txs_to_rebroadcast = responder.get_txs_to_rebroadcast()
    assert txs_to_rebroadcast == list(txs_missing_too_many_conf.keys())


def test_get_completed_trackers(responder, generate_dummy_tracker, monkeypatch):
    # A complete tracker is a tracker whose penalty transaction has been irrevocably resolved (i.e. has reached 100
    # confirmations)

    # We'll create 3 type of txs: irrevocably resolved, confirmed but not irrevocably resolved, and unconfirmed
    trackers_ir_resolved = {uuid4().hex: generate_dummy_tracker() for _ in range(10)}
    trackers_confirmed = {uuid4().hex: generate_dummy_tracker() for _ in range(10)}
    ir_resolved_penalties = [tracker.penalty_txid for _, tracker in trackers_ir_resolved.items()]

    trackers_unconfirmed = {}
    unconfirmed_txs = []
    for commitment_tx in range(10):
        tracker = generate_dummy_tracker()
        unconfirmed_txs.append(tracker.penalty_txid)
        trackers_unconfirmed[uuid4().hex] = tracker

    # Get all the trackers summary to add the to the Responder
    all_trackers_summary = {}
    all_trackers_summary.update(trackers_ir_resolved)
    all_trackers_summary.update(trackers_confirmed)
    all_trackers_summary.update(trackers_unconfirmed)
    for uuid, tracker in all_trackers_summary.items():
        all_trackers_summary[uuid] = tracker.get_summary()

    # Mock the data in the Responder
    monkeypatch.setattr(responder, "unconfirmed_txs", unconfirmed_txs)
    monkeypatch.setattr(responder, "trackers", all_trackers_summary)
    monkeypatch.setattr(
        responder.carrier,
        "get_transaction",
        lambda x: {"confirmations": 100} if x in ir_resolved_penalties else {"confirmations": 99},
    )

    # Let's check
    completed_trackers = responder.get_completed_trackers()
    ended_trackers_keys = list(trackers_ir_resolved.keys())
    assert set(completed_trackers) == set(ended_trackers_keys)

    # Generating 1 additional blocks should also include confirmed
    monkeypatch.setattr(
        responder.carrier,
        "get_transaction",
        lambda x: {"confirmations": 101} if x in ir_resolved_penalties else {"confirmations": 100},
    )

    completed_trackers = responder.get_completed_trackers()
    ended_trackers_keys.extend(list(trackers_confirmed.keys()))
    assert set(completed_trackers) == set(ended_trackers_keys)


def test_get_outdated_trackers(responder, generate_dummy_tracker, monkeypatch):
    # Expired trackers are those whose subscription has reached the expiry block and have not been confirmed.
    # Confirmed trackers that have reached their expiry will be kept until completed

    # Create some trackers and add them to the corresponding user in the Gatekeeper
    outdated_unconfirmed_trackers = {}
    outdated_unconfirmed_trackers_next = {}
    outdated_confirmed_trackers = {}
    unconfirmed_txs = []

    for i in range(20):
        uuid = uuid4().hex
        dummy_tracker = generate_dummy_tracker()

        # Make 10 of them confirmed and 10 of them unconfirmed expiring next block and 10 unconfirmed expiring in two
        if i % 3:
            outdated_unconfirmed_trackers[uuid] = dummy_tracker
            unconfirmed_txs.append(dummy_tracker.penalty_txid)
        elif i % 2:
            outdated_unconfirmed_trackers_next[uuid] = dummy_tracker
            unconfirmed_txs.append(dummy_tracker.penalty_txid)
        else:
            outdated_confirmed_trackers[uuid] = dummy_tracker

    # Get all the trackers summary to add the to the Responder
    all_trackers_summary = {}
    all_trackers_summary.update(outdated_confirmed_trackers)
    all_trackers_summary.update(outdated_unconfirmed_trackers)
    all_trackers_summary.update(outdated_unconfirmed_trackers_next)
    for uuid, tracker in all_trackers_summary.items():
        all_trackers_summary[uuid] = tracker.get_summary()

    # Add the data to the the Gatekeeper and the Responder
    init_block = 0
    monkeypatch.setattr(responder, "trackers", all_trackers_summary)
    monkeypatch.setattr(responder, "unconfirmed_txs", unconfirmed_txs)
    # Mock the expiry for this block, next block and two blocks from now (plus EXPIRY_DELTA)
    monkeypatch.setattr(
        responder.gatekeeper,
        "get_outdated_appointments",
        lambda x: []
        if x == init_block
        else outdated_unconfirmed_trackers
        if x == init_block + 1 + config.get("EXPIRY_DELTA")
        else outdated_unconfirmed_trackers_next,
    )

    # Currently nothing should be outdated
    assert responder.get_outdated_trackers(init_block) == []

    # 1 block (+ EXPIRY_DELTA) afterwards only user1's confirmed trackers should be outdated
    assert responder.get_outdated_trackers(init_block + 1 + config.get("EXPIRY_DELTA")) == list(
        outdated_unconfirmed_trackers.keys()
    )

    # 2 blocks (+ EXPIRY_DELTA) block after user2's should be outdated
    assert responder.get_outdated_trackers(init_block + 2 + config.get("EXPIRY_DELTA")) == list(
        outdated_unconfirmed_trackers_next.keys()
    )


def test_rebroadcast(responder, generate_dummy_tracker, monkeypatch):
    # Rebroadcast will resend the transactions that have missed enough confirmations and reset the confirmation counter
    txs_to_rebroadcast = []
    trackers = [generate_dummy_tracker() for _ in range(20)]

    # Add all trackers to the Responder and flag some as to rebroadcast
    for i, tracker in enumerate(trackers):
        # We'll add the data manually so we don't need to mock all the data structures + db
        responder.add_tracker(
            uuid4().hex,
            tracker.locator,
            tracker.dispute_txid,
            tracker.penalty_txid,
            tracker.penalty_rawtx,
            tracker.user_id,
        )

        # Let's add some of the txs in the rebroadcast list
        if (i % 2) == 0:
            txs_to_rebroadcast.append(tracker.penalty_txid)

    # Mock the interaction with the Carrier
    monkeypatch.setattr(responder.carrier, "send_transaction", mock_receipt_true)

    # Call rebroadcast and and check
    receipts = responder.rebroadcast(txs_to_rebroadcast)
    # All txs should have been delivered and the missed confirmation reset
    for txid, receipt in receipts:
        assert receipt.delivered
        assert txid in txs_to_rebroadcast
        assert responder.missed_confirmations[txid] == 0


# TESTS WITH BITCOIND UNREACHABLE
# We need to test this with a real BlockProcessor


def test_on_sync_bitcoind_crash(responder, block_processor):
    responder.block_processor = block_processor
    chain_tip = responder.block_processor.get_best_block_hash()
    run_test_blocking_command_bitcoind_crash(
        responder.block_processor.bitcoind_reachable, lambda: responder.on_sync(chain_tip)
    )


def test_do_watch_bitcoind_crash(responder, block_processor):
    responder.block_processor = block_processor
    # Let's start to watch
    do_watch_thread = Thread(target=responder.do_watch, daemon=True)
    do_watch_thread.start()
    time.sleep(2)

    # Block the responder
    responder.block_processor.bitcoind_reachable.clear()
    assert responder.block_queue.empty()

    # Mine a block and check how the Responder is blocked processing it
    best_tip = generate_blocks_with_delay(1, 2)[0]
    responder.block_queue.put(best_tip)
    time.sleep(2)
    assert responder.last_known_block != best_tip
    assert responder.block_queue.unfinished_tasks == 1

    # Reestablish the connection and check back
    responder.block_processor.bitcoind_reachable.set()
    time.sleep(2)
    assert responder.last_known_block == best_tip
    assert responder.block_queue.unfinished_tasks == 0
