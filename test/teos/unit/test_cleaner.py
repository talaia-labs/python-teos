import random
from uuid import uuid4

from teos.cleaner import Cleaner
from teos.gatekeeper import UserInfo
from teos.responder import TransactionTracker
from common.appointment import Appointment

from test.teos.unit.conftest import get_random_value_hex

from common.constants import LOCATOR_LEN_BYTES, LOCATOR_LEN_HEX

CONFIRMATIONS = 6
ITEMS = 10
MAX_ITEMS = 100
ITERATIONS = 10


def set_up_appointments(db_manager, total_appointments):
    appointments = dict()
    locator_uuid_map = dict()

    for i in range(total_appointments):
        uuid = uuid4().hex
        locator = get_random_value_hex(LOCATOR_LEN_BYTES)

        appointment = Appointment(locator, None, None)
        appointments[uuid] = {"locator": appointment.locator}
        locator_uuid_map[locator] = [uuid]

        db_manager.store_watcher_appointment(uuid, appointment.to_dict())
        db_manager.create_append_locator_map(locator, uuid)

        # Each locator can have more than one uuid assigned to it.
        if i % 2:
            uuid = uuid4().hex

            appointments[uuid] = {"locator": appointment.locator}
            locator_uuid_map[locator].append(uuid)

            db_manager.store_watcher_appointment(uuid, appointment.to_dict())
            db_manager.create_append_locator_map(locator, uuid)

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
        trackers[uuid] = {"locator": tracker.locator, "penalty_txid": tracker.penalty_txid}
        tx_tracker_map[penalty_txid] = [uuid]

        db_manager.store_responder_tracker(uuid, tracker.to_dict())
        db_manager.create_append_locator_map(tracker.locator, uuid)

        # Each penalty_txid can have more than one uuid assigned to it.
        if i % 2:
            uuid = uuid4().hex

            trackers[uuid] = {"locator": tracker.locator, "penalty_txid": tracker.penalty_txid}
            tx_tracker_map[penalty_txid].append(uuid)

            db_manager.store_responder_tracker(uuid, tracker.to_dict())
            db_manager.create_append_locator_map(tracker.locator, uuid)

    return trackers, tx_tracker_map


def test_delete_appointment_from_memory(db_manager):
    appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)

    for uuid in list(appointments.keys()):
        Cleaner.delete_appointment_from_memory(uuid, appointments, locator_uuid_map)

        # The appointment should have been deleted from memory, but not from the db
        assert uuid not in appointments
        assert db_manager.load_watcher_appointment(uuid) is not None


def test_delete_appointment_from_db(db_manager):
    appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)

    for uuid in list(appointments.keys()):
        Cleaner.delete_appointment_from_db(uuid, db_manager)

        # The appointment should have been deleted from memory, but not from the db
        assert uuid in appointments
        assert db_manager.load_watcher_appointment(uuid) is None


def test_update_delete_db_locator_map(db_manager):
    appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)

    for uuid, appointment in appointments.items():
        locator = appointment.get("locator")
        locator_map_before = db_manager.load_locator_map(locator)
        Cleaner.update_delete_db_locator_map([uuid], locator, db_manager)
        locator_map_after = db_manager.load_locator_map(locator)

        if locator_map_after is None:
            assert locator_map_before is not None

        else:
            assert uuid in locator_map_before and uuid not in locator_map_after


def test_delete_expired_appointment(db_manager):
    for _ in range(ITERATIONS):
        appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)
        expired_appointments = random.sample(list(appointments.keys()), k=ITEMS)

        Cleaner.delete_expired_appointments(expired_appointments, appointments, locator_uuid_map, db_manager)

        assert not set(expired_appointments).issubset(appointments.keys())


def test_delete_completed_appointments(db_manager):
    for _ in range(ITERATIONS):
        appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)
        completed_appointments = random.sample(list(appointments.keys()), k=ITEMS)

        len_before_clean = len(appointments)
        Cleaner.delete_completed_appointments(completed_appointments, appointments, locator_uuid_map, db_manager)

        # ITEMS appointments should have been deleted from memory
        assert len(appointments) == len_before_clean - ITEMS

        # Make sure they are not in the db either
        db_appointments = db_manager.load_watcher_appointments(include_triggered=True)
        assert not set(completed_appointments).issubset(db_appointments)


def test_flag_triggered_appointments(db_manager):
    for _ in range(ITERATIONS):
        appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)
        triggered_appointments = random.sample(list(appointments.keys()), k=ITEMS)

        len_before_clean = len(appointments)
        Cleaner.flag_triggered_appointments(triggered_appointments, appointments, locator_uuid_map, db_manager)

        # ITEMS appointments should have been deleted from memory
        assert len(appointments) == len_before_clean - ITEMS

        # Make sure that all appointments are flagged as triggered in the db
        db_appointments = db_manager.load_all_triggered_flags()
        assert set(triggered_appointments).issubset(db_appointments)


def test_delete_trackers_db_match(db_manager):
    # Completed and expired trackers are deleted using the same method. The only difference is the logging message
    height = 0

    for _ in range(ITERATIONS):
        trackers, tx_tracker_map = set_up_trackers(db_manager, MAX_ITEMS)
        selected_trackers = random.sample(list(trackers.keys()), k=ITEMS)

        completed_trackers = {tracker: 6 for tracker in selected_trackers}

        Cleaner.delete_trackers(completed_trackers, height, trackers, tx_tracker_map, db_manager)

        assert not set(completed_trackers).issubset(trackers.keys())


def test_delete_trackers_no_db_match(db_manager):
    height = 0

    for _ in range(ITERATIONS):
        trackers, tx_tracker_map = set_up_trackers(db_manager, MAX_ITEMS)
        selected_trackers = random.sample(list(trackers.keys()), k=ITEMS)

        # Let's change some uuid's by creating new trackers that are not included in the db and share a penalty_txid
        # with another tracker that is stored in the db.
        for uuid in selected_trackers[: ITEMS // 2]:
            penalty_txid = trackers[uuid].get("penalty_txid")
            dispute_txid = get_random_value_hex(32)
            locator = dispute_txid[:LOCATOR_LEN_HEX]
            new_uuid = uuid4().hex

            trackers[new_uuid] = {"locator": locator, "penalty_txid": penalty_txid}
            tx_tracker_map[penalty_txid].append(new_uuid)
            selected_trackers.append(new_uuid)

        # Let's add some random data
        for i in range(ITEMS // 2):
            uuid = uuid4().hex
            penalty_txid = get_random_value_hex(32)
            dispute_txid = get_random_value_hex(32)
            locator = dispute_txid[:LOCATOR_LEN_HEX]

            trackers[uuid] = {"locator": locator, "penalty_txid": penalty_txid}
            tx_tracker_map[penalty_txid] = [uuid]
            selected_trackers.append(uuid)

        completed_trackers = {tracker: 6 for tracker in selected_trackers}

        # We should be able to delete the correct ones and not fail in the others
        Cleaner.delete_trackers(completed_trackers, height, trackers, tx_tracker_map, db_manager)
        assert not set(completed_trackers).issubset(trackers.keys())


def test_delete_gatekeeper_appointments(gatekeeper):
    # delete_gatekeeper_appointments should delete the appointments from user as long as both exist

    appointments_not_to_delete = {}
    appointments_to_delete = {}
    # Let's add some users and appointments to the Gatekeeper
    for _ in range(10):
        user_id = get_random_value_hex(16)
        # The UserInfo params do not matter much here
        gatekeeper.registered_users[user_id] = UserInfo(available_slots=100, subscription_expiry=0)
        for _ in range(random.randint(0, 10)):
            # Add some appointments
            uuid = get_random_value_hex(16)
            gatekeeper.registered_users[user_id].appointments[uuid] = 1

            if random.randint(0, 1) % 2:
                appointments_to_delete[uuid] = user_id
            else:
                appointments_not_to_delete[uuid] = user_id

    # Now let's delete half of them
    Cleaner.delete_gatekeeper_appointments(gatekeeper, appointments_to_delete)

    all_appointments_gatekeeper = []
    # Let's get all the appointments in the Gatekeeper
    for user_id, user in gatekeeper.registered_users.items():
        all_appointments_gatekeeper.extend(user.appointments)

    # Check that the first half of the appointments are not in the Gatekeeper, but the second half is
    assert not set(appointments_to_delete).issubset(all_appointments_gatekeeper)
    assert set(appointments_not_to_delete).issubset(all_appointments_gatekeeper)
