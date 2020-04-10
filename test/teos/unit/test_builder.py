import pytest
from uuid import uuid4
from queue import Queue

from teos.builder import Builder
from teos.watcher import Watcher
from teos.responder import Responder

from test.teos.unit.conftest import (
    get_random_value_hex,
    generate_dummy_appointment,
    generate_dummy_tracker,
    generate_block,
    bitcoin_cli,
    get_config,
    bitcoind_connect_params,
    generate_keypair,
)

config = get_config()


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
        assert len(appointments_data[uuid].get("encrypted_blob")) == appointment.get("size")
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


def test_update_states_empty_list(db_manager, carrier, block_processor):
    w = Watcher(
        db_manager=db_manager,
        block_processor=block_processor,
        responder=Responder(db_manager, carrier, block_processor),
        sk_der=generate_keypair()[0].to_der(),
        max_appointments=config.get("MAX_APPOINTMENTS"),
        expiry_delta=config.get("EXPIRY_DELTA"),
    )

    missed_blocks_watcher = []
    missed_blocks_responder = [get_random_value_hex(32)]

    # Any combination of empty list must raise a ValueError
    with pytest.raises(ValueError):
        Builder.update_states(w, missed_blocks_watcher, missed_blocks_responder)

    with pytest.raises(ValueError):
        Builder.update_states(w, missed_blocks_responder, missed_blocks_watcher)


def test_update_states_responder_misses_more(run_bitcoind, db_manager, carrier, block_processor):
    w = Watcher(
        db_manager=db_manager,
        block_processor=block_processor,
        responder=Responder(db_manager, carrier, block_processor),
        sk_der=generate_keypair()[0].to_der(),
        max_appointments=config.get("MAX_APPOINTMENTS"),
        expiry_delta=config.get("EXPIRY_DELTA"),
    )

    blocks = []
    for _ in range(5):
        generate_block()
        blocks.append(bitcoin_cli(bitcoind_connect_params).getbestblockhash())

    # Updating the states should bring both to the same last known block.
    w.awake()
    w.responder.awake()
    Builder.update_states(w, blocks, blocks[1:])

    assert db_manager.load_last_block_hash_watcher() == blocks[-1]
    assert w.responder.last_known_block == blocks[-1]


def test_update_states_watcher_misses_more(db_manager, carrier, block_processor):
    # Same as before, but data is now in the Responder
    w = Watcher(
        db_manager=db_manager,
        block_processor=block_processor,
        responder=Responder(db_manager, carrier, block_processor),
        sk_der=generate_keypair()[0].to_der(),
        max_appointments=config.get("MAX_APPOINTMENTS"),
        expiry_delta=config.get("EXPIRY_DELTA"),
    )

    blocks = []
    for _ in range(5):
        generate_block()
        blocks.append(bitcoin_cli(bitcoind_connect_params).getbestblockhash())

    w.awake()
    w.responder.awake()
    Builder.update_states(w, blocks[1:], blocks)

    assert db_manager.load_last_block_hash_watcher() == blocks[-1]
    assert db_manager.load_last_block_hash_responder() == blocks[-1]
