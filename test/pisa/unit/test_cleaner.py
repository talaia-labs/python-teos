import random
from uuid import uuid4

from pisa.responder import TransactionTracker
from pisa.cleaner import Cleaner
from common.appointment import Appointment
from pisa.db_manager import WATCHER_PREFIX

from test.pisa.unit.conftest import get_random_value_hex

from common.constants import LOCATOR_LEN_BYTES, LOCATOR_LEN_HEX

CONFIRMATIONS = 6
ITEMS = 10
MAX_ITEMS = 100
ITERATIONS = 10


# WIP: FIX CLEANER TESTS AFTER ADDING delete_complete_appointment
def set_up_appointments(db_manager, total_appointments):
    appointments = dict()
    locator_uuid_map = dict()

    for i in range(total_appointments):
        uuid = uuid4().hex
        locator = get_random_value_hex(LOCATOR_LEN_BYTES)

        appointment = Appointment(locator, None, None, None, None)
        appointments[uuid] = appointment
        locator_uuid_map[locator] = [uuid]

        db_manager.store_watcher_appointment(uuid, appointment.to_json())
        db_manager.store_update_locator_map(locator, uuid)

        # Each locator can have more than one uuid assigned to it.
        if i % 2:
            uuid = uuid4().hex

            appointments[uuid] = appointment
            locator_uuid_map[locator].append(uuid)

            db_manager.store_watcher_appointment(uuid, appointment.to_json())
            db_manager.store_update_locator_map(locator, uuid)

    return appointments, locator_uuid_map


def set_up_trackers(db_manager, total_trackers):
    trackers = dict()
    tx_tracker_map = dict()

    for i in range(total_trackers):
        uuid = uuid4().hex

        # We use the same txid for penalty and dispute here, it shouldn't matter
        penalty_txid = get_random_value_hex(32)
        dispute_txid = get_random_value_hex(32)
        locator = dispute_txid[:LOCATOR_LEN_HEX]

        # Assign both penalty_txid and dispute_txid the same id (it shouldn't matter)
        tracker = TransactionTracker(locator, dispute_txid, penalty_txid, None, None)
        trackers[uuid] = tracker
        tx_tracker_map[penalty_txid] = [uuid]

        db_manager.store_responder_tracker(uuid, tracker.to_json())
        db_manager.store_update_locator_map(tracker.locator, uuid)

        # Each penalty_txid can have more than one uuid assigned to it.
        if i % 2:
            uuid = uuid4().hex

            trackers[uuid] = tracker
            tx_tracker_map[penalty_txid].append(uuid)

            db_manager.store_responder_tracker(uuid, tracker.to_json())
            db_manager.store_update_locator_map(tracker.locator, uuid)

    return trackers, tx_tracker_map


def test_delete_expired_appointment(db_manager):
    for _ in range(ITERATIONS):
        appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)
        expired_appointments = random.sample(list(appointments.keys()), k=ITEMS)

        Cleaner.delete_expired_appointment(expired_appointments, appointments, locator_uuid_map, db_manager)

        assert not set(expired_appointments).issubset(appointments.keys())


def test_delete_completed_appointments(db_manager):
    appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)
    uuids = list(appointments.keys())

    for uuid in uuids:
        Cleaner.delete_completed_appointment(uuid, appointments, locator_uuid_map, db_manager)

    # All appointments should have been deleted
    assert len(appointments) == 0

    # Make sure that all appointments are flagged as triggered in the db
    db_appointments = db_manager.load_appointments_db(prefix=WATCHER_PREFIX)
    for uuid in uuids:
        assert db_appointments[uuid]["triggered"] is True


def test_delete_completed_trackers_db_match(db_manager):
    height = 0

    for _ in range(ITERATIONS):
        trackers, tx_tracker_map = set_up_trackers(db_manager, MAX_ITEMS)
        selected_trackers = random.sample(list(trackers.keys()), k=ITEMS)

        completed_trackers = [(tracker, 6) for tracker in selected_trackers]

        Cleaner.delete_completed_trackers(completed_trackers, height, trackers, tx_tracker_map, db_manager)

        assert not set(completed_trackers).issubset(trackers.keys())


def test_delete_completed_trackers_no_db_match(db_manager):
    height = 0

    for _ in range(ITERATIONS):
        trackers, tx_tracker_map = set_up_trackers(db_manager, MAX_ITEMS)
        selected_trackers = random.sample(list(trackers.keys()), k=ITEMS)

        # Let's change some uuid's by creating new trackers that are not included in the db and share a penalty_txid
        # with another tracker that is stored in the db.
        for uuid in selected_trackers[: ITEMS // 2]:
            penalty_txid = trackers[uuid].penalty_txid
            dispute_txid = get_random_value_hex(32)
            locator = dispute_txid[:LOCATOR_LEN_HEX]
            new_uuid = uuid4().hex

            trackers[new_uuid] = TransactionTracker(locator, dispute_txid, penalty_txid, None, None)
            tx_tracker_map[penalty_txid].append(new_uuid)
            selected_trackers.append(new_uuid)

        # Let's add some random data
        for i in range(ITEMS // 2):
            uuid = uuid4().hex
            penalty_txid = get_random_value_hex(32)
            dispute_txid = get_random_value_hex(32)
            locator = dispute_txid[:LOCATOR_LEN_HEX]

            trackers[uuid] = TransactionTracker(locator, dispute_txid, penalty_txid, None, None)
            tx_tracker_map[penalty_txid] = [uuid]
            selected_trackers.append(uuid)

        completed_trackers = [(tracker, 6) for tracker in selected_trackers]

        # We should be able to delete the correct ones and not fail in the others
        Cleaner.delete_completed_trackers(completed_trackers, height, trackers, tx_tracker_map, db_manager)
        assert not set(completed_trackers).issubset(trackers.keys())
