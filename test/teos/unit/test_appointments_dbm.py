import json
import pytest
import shutil
from uuid import uuid4

from teos.appointments_dbm import AppointmentsDBM
from teos.appointments_dbm import (
    WATCHER_LAST_BLOCK_KEY,
    RESPONDER_LAST_BLOCK_KEY,
    LOCATOR_MAP_PREFIX,
    TRIGGERED_APPOINTMENTS_PREFIX,
)

from common.constants import LOCATOR_LEN_BYTES

from test.teos.unit.conftest import get_random_value_hex


@pytest.fixture(scope="module")
def watcher_appointments(generate_dummy_appointment):
    return {uuid4().hex: generate_dummy_appointment() for _ in range(10)}


@pytest.fixture(scope="module")
def responder_trackers(generate_dummy_tracker):
    return {uuid4().hex: generate_dummy_tracker().locator for _ in range(10)}


@pytest.fixture
def db_manager(db_name="test_db"):
    manager = AppointmentsDBM(db_name)

    yield manager

    manager.db.close()
    shutil.rmtree(db_name)


def test_load_appointments_db(db_manager):
    # Let's make up a prefix and try to load data from the database using it
    prefix = "XX"
    db_appointments = db_manager.load_appointments_db(prefix)

    assert len(db_appointments) == 0

    # We can add a bunch of data to the db and try again (data is stored in json by the manager)
    local_appointments = {}
    for _ in range(10):
        key = get_random_value_hex(16)
        value = get_random_value_hex(32)
        local_appointments[key] = value

        db_manager.db.put((prefix + key).encode("utf-8"), json.dumps({"value": value}).encode("utf-8"))

    # Check that both keys and values are the same
    db_appointments = db_manager.load_appointments_db(prefix)
    assert db_appointments.keys() == local_appointments.keys()
    values = [appointment["value"] for appointment in db_appointments.values()]
    assert set(values) == set(local_appointments.values()) and (len(values) == len(local_appointments))


def test_get_last_known_block(db_manager):
    # Trying to get any last block for either the Watcher or the Responder should return None for an empty db
    # (the db is freshly created in every test)
    for key in [WATCHER_LAST_BLOCK_KEY, RESPONDER_LAST_BLOCK_KEY]:
        assert db_manager.get_last_known_block(key) is None

    # After saving some block in the db we should get that exact value
    for key in [WATCHER_LAST_BLOCK_KEY, RESPONDER_LAST_BLOCK_KEY]:
        block_hash = get_random_value_hex(32)
        db_manager.db.put(key.encode("utf-8"), block_hash.encode("utf-8"))
        assert db_manager.get_last_known_block(key) == block_hash


def test_load_watcher_appointments_empty(db_manager):
    # Loadings the appointments dict from an empty db should return an empty dict
    assert not db_manager.load_watcher_appointments()


def test_load_responder_trackers_empty(db_manager):
    # Loadings the trackers dict from an empty db should return an empty dict
    assert not db_manager.load_responder_trackers()


def test_load_locator_map_empty(db_manager):
    # Loadings the locators map from an empty db should return an empty dict
    assert not db_manager.load_locator_map(get_random_value_hex(LOCATOR_LEN_BYTES))


def test_create_append_locator_map(db_manager):
    # Test adding a new entry to the locator map
    uuid = uuid4().hex
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    db_manager.create_append_locator_map(locator, uuid)

    # Check that the locator map has been properly stored
    assert db_manager.load_locator_map(locator) == [uuid]

    # If we try to add the same uuid again the list shouldn't change
    db_manager.create_append_locator_map(locator, uuid)
    assert db_manager.load_locator_map(locator) == [uuid]

    # Add another uuid to the same locator and check that it also works
    uuid2 = uuid4().hex
    db_manager.create_append_locator_map(locator, uuid2)

    assert set(db_manager.load_locator_map(locator)) == {uuid, uuid2}


def test_update_locator_map(db_manager):
    # Tests updating an entry from the locator map
    # Let's create a couple of appointments with the same locator and add them to the map
    locator = get_random_value_hex(32)
    uuid1 = uuid4().hex
    uuid2 = uuid4().hex
    db_manager.create_append_locator_map(locator, uuid1)
    db_manager.create_append_locator_map(locator, uuid2)

    # Check that both entries are in the map
    locator_map = db_manager.load_locator_map(locator)
    assert uuid1 in locator_map and uuid2 in locator_map

    # Remove one of the entries and update the map
    locator_map.remove(uuid1)
    db_manager.update_locator_map(locator, locator_map)

    # Check that only one entry is in the map now
    locator_map_after = db_manager.load_locator_map(locator)
    assert uuid1 not in locator_map_after and uuid2 in locator_map_after and len(locator_map_after) == 1


def test_update_locator_map_wong_data(db_manager):
    # Tests updating the locator map with a different list of uuids. An update can only go through if the new data is
    # a subset of the old one

    # Add a map first
    locator = get_random_value_hex(32)
    db_manager.create_append_locator_map(locator, uuid4().hex)
    db_manager.create_append_locator_map(locator, uuid4().hex)
    locator_map = db_manager.load_locator_map(locator)

    # Try to update
    wrong_map_update = [uuid4().hex]
    db_manager.update_locator_map(locator, wrong_map_update)
    locator_map_after = db_manager.load_locator_map(locator)

    assert locator_map_after == locator_map


def test_update_locator_map_empty(db_manager):
    # We shouldn't be able to update a map with an empty list
    locator = get_random_value_hex(32)
    db_manager.create_append_locator_map(locator, uuid4().hex)
    db_manager.create_append_locator_map(locator, uuid4().hex)

    locator_map = db_manager.load_locator_map(locator)
    db_manager.update_locator_map(locator, [])
    locator_map_after = db_manager.load_locator_map(locator)

    assert locator_map_after == locator_map


def test_delete_locator_map(db_manager):
    # Tests the deletion of data in a locator map

    # Add some data to be deleted
    for _ in range(5):
        uuid = uuid4().hex
        locator = get_random_value_hex(LOCATOR_LEN_BYTES)
        db_manager.create_append_locator_map(locator, uuid)

    locator_maps = db_manager.load_appointments_db(prefix=LOCATOR_MAP_PREFIX)

    # Now that there are some locators we can start the test
    assert len(locator_maps) != 0

    for locator, uuids in locator_maps.items():
        assert db_manager.delete_locator_map(locator) is True

    locator_maps = db_manager.load_appointments_db(prefix=LOCATOR_MAP_PREFIX)
    assert len(locator_maps) == 0


def test_delete_locator_map_wrong(db_manager):
    # Keys of wrong type should fail
    assert db_manager.delete_locator_map(42) is False


def test_store_watcher_appointment_wrong(db_manager, watcher_appointments):
    # Trying to store appointments with wrong uuid types should fail
    for _, appointment in watcher_appointments.items():
        assert db_manager.store_watcher_appointment(42, appointment.to_dict()) is False


def test_load_watcher_appointment_wrong(db_manager):
    # Trying to load random keys should fail
    assert db_manager.load_watcher_appointment(get_random_value_hex(16)) is None

    # Same for keys with wrong format
    assert db_manager.load_watcher_appointment(42) is None


def test_store_load_watcher_appointment(db_manager, watcher_appointments):
    # Tests that storing and loading data matches

    # Store the data first
    for uuid, appointment in watcher_appointments.items():
        assert db_manager.store_watcher_appointment(uuid, appointment.to_dict()) is True

    # Load it
    db_watcher_appointments = db_manager.load_watcher_appointments()

    # Check that the two appointment collections are equal by checking:
    # - Their size is equal
    # - Each element in one collection exists in the other

    assert watcher_appointments.keys() == db_watcher_appointments.keys()

    for uuid, appointment in watcher_appointments.items():
        assert appointment.to_dict() == db_watcher_appointments[uuid]


def test_store_load_triggered_appointment(generate_dummy_appointment, db_manager):
    # Check that stored and loaded (triggered) appointments match

    # Create an appointment flagged as triggered
    triggered_appointment = generate_dummy_appointment()
    uuid = uuid4().hex
    assert db_manager.store_watcher_appointment(uuid, triggered_appointment.to_dict()) is True
    # Create the flag
    db_manager.create_triggered_appointment_flag(uuid)

    # The new appointment is grabbed only if we set include_triggered
    assert not db_manager.load_watcher_appointments()
    assert db_manager.load_watcher_appointments(include_triggered=True) == {uuid: triggered_appointment.to_dict()}


def test_store_responder_trackers_wrong(db_manager, responder_trackers):
    # Trying to store tracker with wrong uuid types should fail
    for _, tracker in responder_trackers.items():
        assert db_manager.store_responder_tracker(42, {"value": tracker}) is False


def test_load_responder_tracker_wrong(db_manager):
    # Trying to load random keys should fail
    assert db_manager.load_responder_tracker(get_random_value_hex(16)) is None

    # Same for keys with wrong format
    assert db_manager.load_responder_tracker(42) is None


def test_store_load_responder_trackers(db_manager, responder_trackers):
    # Tests that storing and loading data matches

    # Store the data first
    for key, value in responder_trackers.items():
        assert db_manager.store_responder_tracker(key, {"value": value}) is True

    # Load it
    db_responder_trackers = db_manager.load_responder_trackers()
    values = [tracker["value"] for tracker in db_responder_trackers.values()]

    assert responder_trackers.keys() == db_responder_trackers.keys()
    assert set(responder_trackers.values()) == set(values) and len(responder_trackers) == len(values)


def test_delete_watcher_appointment(db_manager, watcher_appointments):
    # Tests the deletion of appointments

    # Add some data to be deleted
    for uuid, appointment in watcher_appointments.items():
        db_manager.store_watcher_appointment(uuid, appointment.to_dict())

    # Let's delete all the data we added
    for key in watcher_appointments.keys():
        assert db_manager.delete_watcher_appointment(key) is True

    db_watcher_appointments = db_manager.load_watcher_appointments()
    assert len(db_watcher_appointments) == 0


def test_delete_watcher_appointment_wrong(db_manager, watcher_appointments):
    # Trying to delete appointments with keys of wrong type should fail
    assert db_manager.delete_watcher_appointment(42) is False


def test_batch_delete_watcher_appointments(db_manager, watcher_appointments):
    # Tests deleting appointment in batch

    # Let's start by adding a bunch of appointments
    for uuid, appointment in watcher_appointments.items():
        assert db_manager.store_watcher_appointment(uuid, appointment.to_dict()) is True

    first_half = list(watcher_appointments.keys())[: len(watcher_appointments) // 2]
    second_half = list(watcher_appointments.keys())[len(watcher_appointments) // 2 :]  # noqa: E203

    # Let's now delete half of them in a batch update
    db_manager.batch_delete_watcher_appointments(first_half)

    # Check that the first half is not there
    db_watcher_appointments = db_manager.load_watcher_appointments()
    assert not set(db_watcher_appointments.keys()).issuperset(first_half)
    assert set(db_watcher_appointments.keys()).issuperset(second_half)

    # Let's delete the rest
    db_manager.batch_delete_watcher_appointments(second_half)

    # Now there should be no appointments left
    db_watcher_appointments = db_manager.load_watcher_appointments()
    assert not db_watcher_appointments


def test_delete_responder_tracker(db_manager, responder_trackers):
    # Tests the deletion of appointments

    # Add some data to be deleted
    for key, value in responder_trackers.items():
        db_manager.store_responder_tracker(key, {"value": value})

    # Let's delete all the data we added
    for key in responder_trackers.keys():
        assert db_manager.delete_responder_tracker(key) is True

    db_responder_trackers = db_manager.load_responder_trackers()
    assert len(db_responder_trackers) == 0


def test_delete_responder_tracker_wrong(db_manager, responder_trackers):
    # Trying to delete trackers with keys of wrong type should fail
    assert db_manager.delete_responder_tracker(42) is False


def test_batch_delete_responder_trackers(db_manager, responder_trackers):
    # Tests deleting trackers in batch

    # Let's start by adding a bunch of trackers
    for uuid, value in responder_trackers.items():
        assert db_manager.store_responder_tracker(uuid, {"value": value}) is True

    first_half = list(responder_trackers.keys())[: len(responder_trackers) // 2]
    second_half = list(responder_trackers.keys())[len(responder_trackers) // 2 :]  # noqa: E203

    # Let's now delete half of them in a batch update
    db_manager.batch_delete_responder_trackers(first_half)

    # Check that the first half is not there
    db_responder_trackers = db_manager.load_responder_trackers()
    assert not set(db_responder_trackers.keys()).issuperset(first_half)
    assert set(db_responder_trackers.keys()).issuperset(second_half)

    # Let's delete the rest
    db_manager.batch_delete_responder_trackers(second_half)

    # Now there should be no trackers left
    db_responder_trackers = db_manager.load_responder_trackers()
    assert not db_responder_trackers


def test_store_load_last_block_hash_watcher(db_manager):
    # Tests that storing and loading the last known block of the Watcher matches

    # Let's first create a made up block hash
    local_last_block_hash = get_random_value_hex(32)
    assert db_manager.store_last_block_hash_watcher(local_last_block_hash) is True

    # Check that the values match
    db_last_block_hash = db_manager.load_last_block_hash_watcher()
    assert local_last_block_hash == db_last_block_hash


def test_store_last_block_hash_watcher_wrong(db_manager):
    # Trying to store the last block hash with wrong type should fail
    assert db_manager.store_last_block_hash_watcher(42) is False


def test_store_load_last_block_hash_responder(db_manager):
    # Tests that storing and loading the last known block of the Responder matches

    # Let's first create a made up block hash
    local_last_block_hash = get_random_value_hex(32)
    assert db_manager.store_last_block_hash_responder(local_last_block_hash) is True

    # Check that the values match
    db_last_block_hash = db_manager.load_last_block_hash_responder()
    assert local_last_block_hash == db_last_block_hash


def test_store_load_last_block_hash_responder_wrong(db_manager):
    # Trying to store the last block hash with wrong type should fail
    assert db_manager.store_last_block_hash_responder(42) is False


def test_create_triggered_appointment_flag(db_manager):
    # Tests that flags are added

    # Create a new flag and check that it's there
    key = get_random_value_hex(16)
    db_manager.create_triggered_appointment_flag(key)
    assert db_manager.db.get((TRIGGERED_APPOINTMENTS_PREFIX + key).encode("utf-8")) is not None

    # Test to get a random one that we haven't added
    key = get_random_value_hex(16)
    assert db_manager.db.get((TRIGGERED_APPOINTMENTS_PREFIX + key).encode("utf-8")) is None


def test_batch_create_triggered_appointment_flag(db_manager):
    # Tests that flags are added in batch
    flags = [get_random_value_hex(16) for _ in range(10)]

    # Checked that none of the flags is already in the db
    db_flags = db_manager.load_all_triggered_flags()
    assert not db_flags

    # Make sure that they are now
    db_manager.batch_create_triggered_appointment_flag(flags)
    db_flags = db_manager.load_all_triggered_flags()
    assert set(db_flags) == set(flags) and len(db_flags) == len(flags)


def test_load_all_triggered_flags(db_manager):
    # Tests that flags can be loaded from the database

    # First let add some flags
    flags = [get_random_value_hex(16) for _ in range(10)]
    db_manager.batch_create_triggered_appointment_flag(flags)

    # Check that we get exactly what we added
    db_flags = db_manager.load_all_triggered_flags()
    assert set(db_flags) == set(flags) and len(db_flags) == len(flags)


def test_delete_triggered_appointment_flag(db_manager):
    # Tests that the triggers are properly deleted

    # First let add some flags
    flags = [get_random_value_hex(16) for _ in range(10)]
    db_manager.batch_create_triggered_appointment_flag(flags)

    # Delete all entries
    for flag in flags:
        assert db_manager.delete_triggered_appointment_flag(flag) is True

    # Try to load them back
    for flag in flags:
        assert db_manager.db.get((TRIGGERED_APPOINTMENTS_PREFIX + flag).encode("utf-8")) is None


def test_delete_triggered_appointment_flag_wrong(db_manager):
    # Tests that trying to delete keys of wrong type should fail
    assert db_manager.delete_triggered_appointment_flag(42) is False


def test_batch_delete_triggered_appointment_flag(db_manager):
    # Tests that flags are properly deleted in batch

    # Let's add some flags first
    keys = [get_random_value_hex(16) for _ in range(10)]
    db_manager.batch_create_triggered_appointment_flag(keys)

    first_half = keys[: len(keys) // 2]
    second_half = keys[len(keys) // 2 :]  # noqa: E203

    # And now let's delete in batch
    db_manager.batch_delete_triggered_appointment_flag(first_half)
    db_flags = db_manager.load_all_triggered_flags()

    # The first half should be gone
    assert not set(db_flags).issuperset(first_half)
    assert set(db_flags).issuperset(second_half)

    # Delete the rest and check
    db_manager.batch_delete_triggered_appointment_flag(second_half)
    assert not db_manager.load_all_triggered_flags()
