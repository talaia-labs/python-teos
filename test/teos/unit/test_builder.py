import pytest
from uuid import uuid4
from queue import Queue

from teos.builder import Builder
from test.teos.unit.conftest import get_random_value_hex

# FIXME: IMPROVE THE COMMENTS IN THIS SUITE


def test_build_appointments(generate_dummy_appointment):
    # build_appointments builds two dictionaries: appointments (uuid:ExtendedAppointment) and locator_uuid_map
    # (locator:uuid). These are populated with data pulled from the database and used as initial state by the Watcher
    # during bootstrap
    appointments_data = {}

    # Create some appointment data
    for i in range(10):
        appointment = generate_dummy_appointment()
        uuid = uuid4().hex

        appointments_data[uuid] = appointment.to_dict()

        # Add some additional appointments that share the same locator to test all the builder's cases
        if i % 2 == 0:
            locator = appointment.locator
            appointment = generate_dummy_appointment()
            uuid = uuid4().hex
            appointment.locator = locator

            appointments_data[uuid] = appointment.to_dict()

    # Use the builder to create the data structures
    appointments, locator_uuid_map = Builder.build_appointments(appointments_data)

    # Check that the created appointments match the data
    for uuid, appointment in appointments.items():
        assert uuid in appointments_data.keys()
        assert appointments_data[uuid].get("locator") == appointment.get("locator")
        assert appointments_data[uuid].get("user_id") == appointment.get("user_id")
        assert uuid in locator_uuid_map[appointment.get("locator")]


def test_build_trackers(generate_dummy_tracker):
    # build_trackers builds two dictionaries: trackers (uuid: TransactionTracker) and tx_tracker_map (txid:uuid)
    # These are populated with data pulled from the database and used as initial state by the Responder during bootstrap
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
        assert tracker.get("user_id") == trackers_data[uuid].get("user_id")
        assert uuid in tx_tracker_map[tracker.get("penalty_txid")]


def test_populate_block_queue():
    # populate_block_queue sets the initial state of the Watcher / Responder block queue

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


def test_update_states_empty_list():
    # update_states feed data to both the Watcher and the Responder block queue and waits until it is processed. It is
    # used to bring both components up to date during bootstrap. This is only used iof both have missed blocks,
    # otherwise populate_block_queue must be used.

    # Test the case where one of the components does not have any data to update with

    watcher_queue = Queue()
    responder_queue = Queue()
    missed_blocks_watcher = []
    missed_blocks_responder = [get_random_value_hex(32)]

    # Any combination of empty list must raise a ValueError
    with pytest.raises(ValueError):
        Builder.update_states(watcher_queue, responder_queue, missed_blocks_watcher, missed_blocks_responder)

    with pytest.raises(ValueError):
        Builder.update_states(watcher_queue, responder_queue, missed_blocks_responder, missed_blocks_watcher)


def test_update_states_responder_misses_more(monkeypatch):
    # Test the case where both components have data that need to be updated, but the Responder has more.
    blocks = [get_random_value_hex(32) for _ in range(5)]
    watcher_queue = Queue()
    responder_queue = Queue()

    # Monkeypatch so there's no join, since the queues are not tied to a Watcher and a Responder for the test
    monkeypatch.setattr(watcher_queue, "join", lambda: None)
    monkeypatch.setattr(responder_queue, "join", lambda: None)
    Builder.update_states(watcher_queue, responder_queue, blocks, blocks[1:])

    assert responder_queue.queue.pop() == blocks[-1]
    assert watcher_queue.queue.pop() == blocks[-1]


def test_update_states_watcher_misses_more(monkeypatch):
    # Test the case where both components have data that need to be updated, but the Watcher has more.
    blocks = [get_random_value_hex(32) for _ in range(5)]
    watcher_queue = Queue()
    responder_queue = Queue()

    # Monkeypatch so there's no join, since the queues are not tied to a Watcher and a Responder for the test
    monkeypatch.setattr(watcher_queue, "join", lambda: None)
    monkeypatch.setattr(responder_queue, "join", lambda: None)
    Builder.update_states(watcher_queue, responder_queue, blocks[1:], blocks)

    assert responder_queue.queue.pop() == blocks[-1]
    assert watcher_queue.queue.pop() == blocks[-1]
