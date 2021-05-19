import shutil
import pytest
import random
import itertools
from uuid import uuid4

from teos.cleaner import Cleaner
from teos.users_dbm import UsersDBM
from teos.gatekeeper import UserInfo
from teos.responder import TransactionTracker
from teos.appointments_dbm import AppointmentsDBM

from common.appointment import Appointment
from common.constants import LOCATOR_LEN_BYTES, LOCATOR_LEN_HEX

from test.teos.unit.conftest import get_random_value_hex

flatten = itertools.chain.from_iterable

CONFIRMATIONS = 6
ITEMS = 10
MAX_ITEMS = 100
ITERATIONS = 10


@pytest.fixture(scope="module")
def db_manager(db_name="test_db"):
    manager = AppointmentsDBM(db_name)

    yield manager

    manager.db.close()
    shutil.rmtree(db_name)


@pytest.fixture(scope="module")
def users_db_manager(db_name="test_users_db"):
    manager = UsersDBM(db_name)

    yield manager

    manager.db.close()
    shutil.rmtree(db_name)


# Adds appointment data in the data structures for the cleaner to delete
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

        # Each locator can have more than one uuid assigned to it.
        if i % 2:
            uuid = uuid4().hex

            appointments[uuid] = {"locator": appointment.locator}
            locator_uuid_map[locator].append(uuid)

            db_manager.store_watcher_appointment(uuid, appointment.to_dict())

    return appointments, locator_uuid_map


# Adds trackers data in the data structures for the cleaner to delete
def set_up_trackers(db_manager, total_trackers):
    trackers = dict()
    tx_tracker_map = dict()

    for i in range(total_trackers):
        uuid = uuid4().hex

        # We use the same txid for penalty and dispute here, it shouldn't matter
        penalty_txid = get_random_value_hex(32)
        dispute_txid = get_random_value_hex(32)
        locator = dispute_txid[:LOCATOR_LEN_HEX]

        # Appointment data
        appointment = Appointment(locator, None, None)

        # Store the data in the database and create a flag
        db_manager.store_watcher_appointment(uuid, appointment.to_dict())
        db_manager.create_triggered_appointment_flag(uuid)

        # Assign both penalty_txid and dispute_txid the same id (it shouldn't matter)
        tracker = TransactionTracker(locator, dispute_txid, penalty_txid, None, None)
        trackers[uuid] = {"locator": tracker.locator, "penalty_txid": tracker.penalty_txid}
        tx_tracker_map[penalty_txid] = [uuid]

        db_manager.store_responder_tracker(uuid, tracker.to_dict())

        # Each penalty_txid can have more than one uuid assigned to it.
        if i % 2:
            uuid = uuid4().hex

            trackers[uuid] = {"locator": tracker.locator, "penalty_txid": tracker.penalty_txid}
            tx_tracker_map[penalty_txid].append(uuid)

            db_manager.store_responder_tracker(uuid, tracker.to_dict())

            # Add them to the Watcher's db too
            db_manager.store_watcher_appointment(uuid, appointment.to_dict())
            db_manager.create_triggered_appointment_flag(uuid)

    return trackers, tx_tracker_map


def setup_users(users_db_manager, total_users):
    registered_users = {}

    for _ in range(total_users):
        user_id = "02" + get_random_value_hex(32)
        # The UserInfo params do not matter much here
        user_info = UserInfo(available_slots=100, subscription_expiry=0)
        registered_users[user_id] = user_info

        # Add some appointments
        for _ in range(random.randint(0, 10)):
            uuid = get_random_value_hex(16)
            registered_users[user_id].appointments[uuid] = 1

        users_db_manager.store_user(user_id, user_info.to_dict())

    return registered_users


def test_delete_appointment_from_memory(db_manager):
    # Tests deleting appointments only from memory
    appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)

    for uuid in list(appointments.keys()):
        Cleaner.delete_appointment_from_memory(uuid, appointments, locator_uuid_map)

        # The appointment should have been deleted from memory, but not from the db
        assert uuid not in appointments
        assert db_manager.load_watcher_appointment(uuid) is not None


def test_delete_appointment_from_db(db_manager):
    # Tests deleting appointments only from the database
    appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)

    for uuid in list(appointments.keys()):
        Cleaner.delete_appointment_from_db(uuid, db_manager)

        # The appointment should have been deleted from the database, but not from memory
        assert uuid in appointments
        assert db_manager.load_watcher_appointment(uuid) is None


def test_delete_appointments(db_manager):
    # Tests deleting appointment data both from memory and the database
    for _ in range(ITERATIONS):
        appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)
        outdated_appointments = random.sample(list(appointments.keys()), k=ITEMS)

        # Check that the data is there before deletion
        all_uuids = list(flatten(locator_uuid_map.values()))
        assert set(outdated_appointments).issubset(appointments.keys())
        assert set(outdated_appointments).issubset(all_uuids)

        db_appointments = db_manager.load_watcher_appointments()
        assert set(outdated_appointments).issubset(db_appointments.keys())

        # Delete
        Cleaner.delete_appointments(outdated_appointments, appointments, locator_uuid_map, db_manager)

        # Data is not in memory anymore
        all_uuids = list(flatten(locator_uuid_map.values()))
        assert not set(outdated_appointments).issubset(appointments.keys())
        assert not set(outdated_appointments).issubset(all_uuids)

        # And neither is in the database
        db_appointments = db_manager.load_watcher_appointments()
        assert not set(outdated_appointments).issubset(db_appointments.keys())


def test_flag_triggered_appointments(db_manager):
    # Test that when an appointment is flagged and triggered it is deleted from memory and the flags are added to the db
    for _ in range(ITERATIONS):
        appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)
        triggered_appointments = random.sample(list(appointments.keys()), k=ITEMS)

        # Flag the appointments
        Cleaner.flag_triggered_appointments(triggered_appointments, appointments, locator_uuid_map, db_manager)

        # Check that the flagged appointments are not in memory anymore
        assert not set(triggered_appointments).issubset(appointments)

        # Make sure that all appointments are flagged as triggered in the db
        db_appointments = db_manager.load_all_triggered_flags()
        assert set(triggered_appointments).issubset(db_appointments)


def test_delete_trackers(db_manager):
    # Tests de deletion of trackers
    # Completed and outdated trackers are deleted using the same method. The only difference is the logging message
    height = 0

    for _ in range(ITERATIONS):
        trackers, tx_tracker_map = set_up_trackers(db_manager, MAX_ITEMS)
        selected_trackers = random.sample(list(trackers.keys()), k=ITEMS)

        # Delete the selected trackers {uuid:confirmation_count}
        completed_trackers = {tracker: 6 for tracker in selected_trackers}
        Cleaner.delete_trackers(completed_trackers, height, trackers, tx_tracker_map, db_manager)

        # Check that the data is not in memory anymore
        all_trackers = list(flatten(tx_tracker_map.values()))
        assert not set(completed_trackers).issubset(trackers)
        assert not set(completed_trackers).issubset(all_trackers)

        # And neither is in the db
        db_trackers = db_manager.load_responder_trackers()
        assert not set(completed_trackers).issubset(db_trackers)

        # Check that the data has also been removed from the Watchers db (appointment and triggered flag)
        all_appointments = db_manager.load_watcher_appointments(include_triggered=True)
        all_flags = db_manager.load_all_triggered_flags()

        assert not set(completed_trackers).issubset(all_appointments)
        assert not set(completed_trackers).issubset(all_flags)


def test_delete_gatekeeper_appointments(users_db_manager):
    # Tests that the Cleaner properly deletes the appointment data from the Gatekeeper structures (both memory and db)
    appointments_not_to_delete = {}
    appointments_to_delete = {}

    # Let's mock adding some users and appointments to the Gatekeeper (memory and db)
    registered_users = setup_users(users_db_manager, MAX_ITEMS)

    for user_id, user_info in registered_users.items():
        for uuid in user_info.appointments.keys():
            if random.randint(0, 1) % 2:
                appointments_to_delete[uuid] = user_id
            else:
                appointments_not_to_delete[uuid] = user_id

    # Now let's delete half of them
    Cleaner.delete_gatekeeper_appointments(appointments_to_delete, registered_users, users_db_manager)

    # Let's get all the appointments in the Gatekeeper
    all_appointments_gatekeeper = list(flatten(user.appointments for _, user in registered_users.items()))

    # Check that the first half of the appointments are not in the Gatekeeper, but the second half is
    assert not set(appointments_to_delete).issubset(all_appointments_gatekeeper)
    assert set(appointments_not_to_delete).issubset(all_appointments_gatekeeper)

    # Also check in the database
    db_user_data = users_db_manager.load_all_users()
    all_appointments_db = [user_data.get("appointments") for user_data in db_user_data.values()]
    all_appointments_db = list(flatten(all_appointments_db))
    assert not set(appointments_to_delete).issubset(all_appointments_db)
    assert set(appointments_not_to_delete).issubset(all_appointments_db)


def test_delete_outdated_users(users_db_manager):
    # Tests the deletion of users whose subscription has outdated (subscription expires now)

    # Let's mock adding some users and appointments to the Gatekeeper (memory and db)
    registered_users = setup_users(users_db_manager, MAX_ITEMS)

    # Delete the users
    to_be_deleted = list(registered_users.keys())
    Cleaner.delete_outdated_users(to_be_deleted, registered_users, users_db_manager)

    # Check that the users are not in the gatekeeper anymore
    for user_id in to_be_deleted:
        assert user_id not in registered_users
        assert not users_db_manager.load_user(user_id)
