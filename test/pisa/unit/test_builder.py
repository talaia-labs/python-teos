import pytest
from uuid import uuid4
from queue import Queue

from pisa.builder import Builder
from pisa.watcher import Watcher
from test.pisa.unit.conftest import (
    get_random_value_hex,
    generate_dummy_appointment,
    generate_dummy_tracker,
    generate_block,
    bitcoin_cli,
    get_config,
)


def test_build_appointments():
    appointments_data = {}

    # Create some appointment data
    for i in range(10):
        appointment, _ = generate_dummy_appointment(real_height=False)
        uuid = uuid4().hex

        appointments_data[uuid] = appointment.to_dict()

        # Add some additional appointments that share the same locator to test all the builder's cases
        if i % 2 == 0:
            locator = appointment.locator
            appointment, _ = generate_dummy_appointment(real_height=False)
            uuid = uuid4().hex
            appointment.locator = locator

            appointments_data[uuid] = appointment.to_dict()

    # Use the builder to create the data structures
    appointments, locator_uuid_map = Builder.build_appointments(appointments_data)

    # Check that the created appointments match the data
    for uuid, appointment in appointments.items():
        assert uuid in appointments_data.keys()
        assert appointments_data[uuid].get("locator") == appointment.get("locator")
        assert appointments_data[uuid].get("end_time") == appointment.get("end_time")
        assert uuid in locator_uuid_map[appointment.get("locator")]


def test_build_trackers():
    trackers_data = {}

    # Create some trackers data
    for i in range(10):
        tracker = generate_dummy_tracker()

        trackers_data[uuid4().hex] = tracker.to_dict()

        # Add some additional trackers that share the same locator to test all the builder's cases
        if i % 2 == 0:
            penalty_txid = tracker.penalty_txid
            tracker = generate_dummy_tracker()
            tracker.penalty_txid = penalty_txid

            trackers_data[uuid4().hex] = tracker.to_dict()

    trackers, tx_tracker_map = Builder.build_trackers(trackers_data)

    # Check that the built trackers match the data
    for uuid, tracker in trackers.items():
        assert uuid in trackers_data.keys()

        assert tracker.get("penalty_txid") == trackers_data[uuid].get("penalty_txid")
        assert tracker.get("locator") == trackers_data[uuid].get("locator")
        assert tracker.get("appointment_end") == trackers_data[uuid].get("appointment_end")
        assert uuid in tx_tracker_map[tracker.get("penalty_txid")]


def test_populate_block_queue():
    # Create some random block hashes and construct the queue with them
    blocks = [get_random_value_hex(32) for _ in range(10)]
    queue = Queue()
    Builder.populate_block_queue(queue, blocks)

    # Make sure every block is in the queue and that there are not additional ones
    while not queue.empty():
        block = queue.get()
        assert block in blocks
        blocks.remove(block)

    assert len(blocks) == 0


def test_update_states_empty_list(db_manager):
    w = Watcher(db_manager=db_manager, chain_monitor=None, sk_der=None, config=None)

    missed_blocks_watcher = []
    missed_blocks_responder = [get_random_value_hex(32)]

    # Any combination of empty list must raise a ValueError
    with pytest.raises(ValueError):
        Builder.update_states(w, missed_blocks_watcher, missed_blocks_responder)

    with pytest.raises(ValueError):
        Builder.update_states(w, missed_blocks_responder, missed_blocks_watcher)


def test_update_states_different_sizes(run_bitcoind, db_manager, chain_monitor):
    w = Watcher(db_manager=db_manager, chain_monitor=chain_monitor, sk_der=None, config=get_config())
    chain_monitor.attach_watcher(w.responder, True)
    chain_monitor.attach_responder(w.responder, True)

    # For the states to be updated data needs to be present in the actors (either appointments or trackers).
    # Let's start from the Watcher. We add one appointment and mine some blocks that both are gonna miss.
    w.appointments[uuid4().hex] = {"locator": get_random_value_hex(16), "end_time": 200}

    blocks = []
    for _ in range(5):
        generate_block()
        blocks.append(bitcoin_cli().getbestblockhash())

    # Updating the states should bring both to the same last known block. The Watcher's is stored in the db since it has
    # gone over do_watch, whereas the Responders in only updated by update state.
    Builder.update_states(w, blocks, blocks[1:])

    assert db_manager.load_last_block_hash_watcher() == blocks[-1]
    assert w.responder.last_known_block == blocks[-1]

    # If both have work, both last known blocks are updated
    w.sleep()
    w.responder.sleep()

    w.responder.trackers[uuid4().hex] = {
        "penalty_txid": get_random_value_hex(32),
        "locator": get_random_value_hex(16),
        "appointment_end": 200,
    }

    blocks = []
    for _ in range(5):
        generate_block()
        blocks.append(bitcoin_cli().getbestblockhash())

    Builder.update_states(w, blocks[1:], blocks)
    assert db_manager.load_last_block_hash_watcher() == blocks[-1]
    assert db_manager.load_last_block_hash_responder() == blocks[-1]

    # Let's try the opposite of the first test (Responder with data, Watcher without)
    w.sleep()
    w.responder.sleep()

    w.appointments = {}
    last_block_prev = blocks[-1]

    blocks = []
    for _ in range(5):
        generate_block()
        blocks.append(bitcoin_cli().getbestblockhash())

    # The Responder should have been brought up to date via do_watch, whereas the Watcher's last known block hash't
    # change. The Watcher does not keep track of reorgs, so if he has no work to do he does not even update the last
    # known block.
    Builder.update_states(w, blocks[1:], blocks)
    assert db_manager.load_last_block_hash_watcher() == last_block_prev
    assert db_manager.load_last_block_hash_responder() == blocks[-1]


def test_update_states_same_sizes(db_manager, chain_monitor):
    # The exact same behaviour of the last test is expected here, since different sizes are even using
    # populate_block_queue and then run with the same list size.
    w = Watcher(db_manager=db_manager, chain_monitor=chain_monitor, sk_der=None, config=get_config())
    chain_monitor.attach_watcher(w.responder, True)
    chain_monitor.attach_responder(w.responder, True)

    # For the states to be updated data needs to be present in the actors (either appointments or trackers).
    # Let's start from the Watcher. We add one appointment and mine some blocks that both are gonna miss.
    w.appointments[uuid4().hex] = {"locator": get_random_value_hex(16), "end_time": 200}

    blocks = []
    for _ in range(5):
        generate_block()
        blocks.append(bitcoin_cli().getbestblockhash())

    Builder.update_states(w, blocks, blocks)

    assert db_manager.load_last_block_hash_watcher() == blocks[-1]
    assert w.responder.last_known_block == blocks[-1]

    # If both have work, both last known blocks are updated
    w.sleep()
    w.responder.sleep()

    w.responder.trackers[uuid4().hex] = {
        "penalty_txid": get_random_value_hex(32),
        "locator": get_random_value_hex(16),
        "appointment_end": 200,
    }

    blocks = []
    for _ in range(5):
        generate_block()
        blocks.append(bitcoin_cli().getbestblockhash())

    Builder.update_states(w, blocks, blocks)
    assert db_manager.load_last_block_hash_watcher() == blocks[-1]
    assert db_manager.load_last_block_hash_responder() == blocks[-1]

    # Let's try the opposite of the first test (Responder with data, Watcher without)
    w.sleep()
    w.responder.sleep()

    w.appointments = {}
    last_block_prev = blocks[-1]

    blocks = []
    for _ in range(5):
        generate_block()
        blocks.append(bitcoin_cli().getbestblockhash())

    # The Responder should have been brought up to date via do_watch, whereas the Watcher's last known block hash't
    # change. The Watcher does not keep track of reorgs, so if he has no work to do he does not even update the last
    # known block.
    Builder.update_states(w, blocks, blocks)
    assert db_manager.load_last_block_hash_watcher() == last_block_prev
    assert db_manager.load_last_block_hash_responder() == blocks[-1]
