from uuid import uuid4

from pisa.builder import Builder
from test.unit.conftest import get_random_value_hex, generate_dummy_appointment, generate_dummy_tracker


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
        assert appointments_data[uuid] == appointment.to_dict()
        assert uuid in locator_uuid_map[appointment.locator]


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
        tracker_dict = tracker.to_dict()

        # The locator is not part of the tracker_data found in the database (for now)
        assert trackers_data[uuid] == tracker_dict
        assert uuid in tx_tracker_map[tracker.penalty_txid]


def test_build_block_queue():
    # Create some random block hashes and construct the queue with them
    blocks = [get_random_value_hex(32) for _ in range(10)]
    queue = Builder.build_block_queue(blocks)

    # Make sure every block is in the queue and that there are not additional ones
    while not queue.empty():
        block = queue.get()
        assert block in blocks
        blocks.remove(block)

    assert len(blocks) == 0
