import os
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

from test.teos.unit.conftest import get_random_value_hex, generate_dummy_appointment


@pytest.fixture(scope="module")
def watcher_appointments():
    return {uuid4().hex: generate_dummy_appointment(real_height=False)[0] for _ in range(10)}


@pytest.fixture(scope="module")
def responder_trackers():
    return {get_random_value_hex(16): get_random_value_hex(32) for _ in range(10)}


def open_create_db(db_path):

    try:
        db_manager = AppointmentsDBM(db_path)

        return db_manager

    except ValueError:
        return False


def test_load_appointments_db(db_manager):
    # Let's made up a prefix and try to load data from the database using it
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

    db_appointments = db_manager.load_appointments_db(prefix)

    # Check that both keys and values are the same
    assert db_appointments.keys() == local_appointments.keys()

    values = [appointment["value"] for appointment in db_appointments.values()]
    assert set(values) == set(local_appointments.values()) and (len(values) == len(local_appointments))


def test_get_last_known_block():
    db_path = "empty_db"

    # First we check if the db exists, and if so we delete it
    if os.path.isdir(db_path):
        shutil.rmtree(db_path)

    # Check that the db can be created if it does not exist
    db_manager = open_create_db(db_path)

    # Trying to get any last block for either the watcher or the responder should return None for an empty db

    for key in [WATCHER_LAST_BLOCK_KEY, RESPONDER_LAST_BLOCK_KEY]:
        assert db_manager.get_last_known_block(key) is None

    # After saving some block in the db we should get that exact value
    for key in [WATCHER_LAST_BLOCK_KEY, RESPONDER_LAST_BLOCK_KEY]:
        block_hash = get_random_value_hex(32)
        db_manager.db.put(key.encode("utf-8"), block_hash.encode("utf-8"))
        assert db_manager.get_last_known_block(key) == block_hash

    # Removing test db
    shutil.rmtree(db_path)


def test_load_watcher_appointments_empty(db_manager):
    assert len(db_manager.load_watcher_appointments()) == 0


def test_load_responder_trackers_empty(db_manager):
    assert len(db_manager.load_responder_trackers()) == 0


def test_load_locator_map_empty(db_manager):
    assert db_manager.load_locator_map(get_random_value_hex(LOCATOR_LEN_BYTES)) is None


def test_create_append_locator_map(db_manager):
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

    assert set(db_manager.load_locator_map(locator)) == set([uuid, uuid2])


def test_update_locator_map(db_manager):
    # Let's create a couple of appointments with the same locator
    locator = get_random_value_hex(32)
    uuid1 = uuid4().hex
    uuid2 = uuid4().hex
    db_manager.create_append_locator_map(locator, uuid1)
    db_manager.create_append_locator_map(locator, uuid2)

    locator_map = db_manager.load_locator_map(locator)
    assert uuid1 in locator_map

    locator_map.remove(uuid1)
    db_manager.update_locator_map(locator, locator_map)

    locator_map_after = db_manager.load_locator_map(locator)
    assert uuid1 not in locator_map_after and uuid2 in locator_map_after and len(locator_map_after) == 1


def test_update_locator_map_wong_data(db_manager):
    # Let's try to update the locator map with a different list of uuids
    locator = get_random_value_hex(32)
    db_manager.create_append_locator_map(locator, uuid4().hex)
    db_manager.create_append_locator_map(locator, uuid4().hex)

    locator_map = db_manager.load_locator_map(locator)
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
    locator_maps = db_manager.load_appointments_db(prefix=LOCATOR_MAP_PREFIX)
    assert len(locator_maps) != 0

    for locator, uuids in locator_maps.items():
        db_manager.delete_locator_map(locator)

    locator_maps = db_manager.load_appointments_db(prefix=LOCATOR_MAP_PREFIX)
    assert len(locator_maps) == 0


def test_store_load_watcher_appointment(db_manager, watcher_appointments):
    for uuid, appointment in watcher_appointments.items():
        db_manager.store_watcher_appointment(uuid, appointment.to_dict())

    db_watcher_appointments = db_manager.load_watcher_appointments()

    # Check that the two appointment collections are equal by checking:
    # - Their size is equal
    # - Each element in one collection exists in the other

    assert watcher_appointments.keys() == db_watcher_appointments.keys()

    for uuid, appointment in watcher_appointments.items():
        assert appointment.to_dict() == db_watcher_appointments[uuid]


def test_store_load_triggered_appointment(db_manager):
    db_watcher_appointments = db_manager.load_watcher_appointments()
    db_watcher_appointments_with_triggered = db_manager.load_watcher_appointments(include_triggered=True)

    assert db_watcher_appointments == db_watcher_appointments_with_triggered

    # Create an appointment flagged as triggered
    triggered_appointment, _ = generate_dummy_appointment(real_height=False)
    uuid = uuid4().hex
    db_manager.store_watcher_appointment(uuid, triggered_appointment.to_dict())
    db_manager.create_triggered_appointment_flag(uuid)

    # The new appointment is grabbed only if we set include_triggered
    assert db_watcher_appointments == db_manager.load_watcher_appointments()
    assert uuid in db_manager.load_watcher_appointments(include_triggered=True)


def test_store_load_responder_trackers(db_manager, responder_trackers):
    for key, value in responder_trackers.items():
        db_manager.store_responder_tracker(key, {"value": value})

    db_responder_trackers = db_manager.load_responder_trackers()

    values = [tracker["value"] for tracker in db_responder_trackers.values()]

    assert responder_trackers.keys() == db_responder_trackers.keys()
    assert set(responder_trackers.values()) == set(values) and len(responder_trackers) == len(values)


def test_delete_watcher_appointment(db_manager, watcher_appointments):
    # Let's delete all we added
    db_watcher_appointments = db_manager.load_watcher_appointments(include_triggered=True)
    assert len(db_watcher_appointments) != 0

    for key in watcher_appointments.keys():
        db_manager.delete_watcher_appointment(key)

    db_watcher_appointments = db_manager.load_watcher_appointments()
    assert len(db_watcher_appointments) == 0


def test_batch_delete_watcher_appointments(db_manager, watcher_appointments):
    # Let's start by adding a bunch of appointments
    for uuid, appointment in watcher_appointments.items():
        db_manager.store_watcher_appointment(uuid, appointment.to_dict())

    first_half = list(watcher_appointments.keys())[: len(watcher_appointments) // 2]
    second_half = list(watcher_appointments.keys())[len(watcher_appointments) // 2 :]

    # Let's now delete half of them in a batch update
    db_manager.batch_delete_watcher_appointments(first_half)

    db_watcher_appointments = db_manager.load_watcher_appointments()
    assert not set(db_watcher_appointments.keys()).issuperset(first_half)
    assert set(db_watcher_appointments.keys()).issuperset(second_half)

    # Let's delete the rest
    db_manager.batch_delete_watcher_appointments(second_half)

    # Now there should be no appointments left
    db_watcher_appointments = db_manager.load_watcher_appointments()
    assert not db_watcher_appointments


def test_delete_responder_tracker(db_manager, responder_trackers):
    # Same for the responder
    db_responder_trackers = db_manager.load_responder_trackers()
    assert len(db_responder_trackers) != 0

    for key in responder_trackers.keys():
        db_manager.delete_responder_tracker(key)

    db_responder_trackers = db_manager.load_responder_trackers()
    assert len(db_responder_trackers) == 0


def test_batch_delete_responder_trackers(db_manager, responder_trackers):
    # Let's start by adding a bunch of appointments
    for uuid, value in responder_trackers.items():
        db_manager.store_responder_tracker(uuid, {"value": value})

    first_half = list(responder_trackers.keys())[: len(responder_trackers) // 2]
    second_half = list(responder_trackers.keys())[len(responder_trackers) // 2 :]

    # Let's now delete half of them in a batch update
    db_manager.batch_delete_responder_trackers(first_half)

    db_responder_trackers = db_manager.load_responder_trackers()
    assert not set(db_responder_trackers.keys()).issuperset(first_half)
    assert set(db_responder_trackers.keys()).issuperset(second_half)

    # Let's delete the rest
    db_manager.batch_delete_responder_trackers(second_half)

    # Now there should be no trackers left
    db_responder_trackers = db_manager.load_responder_trackers()
    assert not db_responder_trackers


def test_store_load_last_block_hash_watcher(db_manager):
    # Let's first create a made up block hash
    local_last_block_hash = get_random_value_hex(32)
    db_manager.store_last_block_hash_watcher(local_last_block_hash)

    db_last_block_hash = db_manager.load_last_block_hash_watcher()

    assert local_last_block_hash == db_last_block_hash


def test_store_load_last_block_hash_responder(db_manager):
    # Same for the responder
    local_last_block_hash = get_random_value_hex(32)
    db_manager.store_last_block_hash_responder(local_last_block_hash)

    db_last_block_hash = db_manager.load_last_block_hash_responder()

    assert local_last_block_hash == db_last_block_hash


def test_create_triggered_appointment_flag(db_manager):
    # Test that flags are added
    key = get_random_value_hex(16)
    db_manager.create_triggered_appointment_flag(key)

    assert db_manager.db.get((TRIGGERED_APPOINTMENTS_PREFIX + key).encode("utf-8")) is not None

    # Test to get a random one that we haven't added
    key = get_random_value_hex(16)
    assert db_manager.db.get((TRIGGERED_APPOINTMENTS_PREFIX + key).encode("utf-8")) is None


def test_batch_create_triggered_appointment_flag(db_manager):
    # Test that flags are added in batch
    keys = [get_random_value_hex(16) for _ in range(10)]

    # Checked that non of the flags is already in the db
    db_flags = db_manager.load_all_triggered_flags()
    assert not set(db_flags).issuperset(keys)

    # Make sure that they are now
    db_manager.batch_create_triggered_appointment_flag(keys)
    db_flags = db_manager.load_all_triggered_flags()
    assert set(db_flags).issuperset(keys)


def test_load_all_triggered_flags(db_manager):
    # There should be a some flags in the db from the previous tests. Let's load them
    flags = db_manager.load_all_triggered_flags()

    # We can add another flag and see that there's two now
    new_uuid = uuid4().hex
    db_manager.create_triggered_appointment_flag(new_uuid)
    flags.append(new_uuid)

    assert set(db_manager.load_all_triggered_flags()) == set(flags)


def test_delete_triggered_appointment_flag(db_manager):
    # Test data is properly deleted.
    keys = db_manager.load_all_triggered_flags()

    # Delete all entries
    for k in keys:
        db_manager.delete_triggered_appointment_flag(k)

    # Try to load them back
    for k in keys:
        assert db_manager.db.get((TRIGGERED_APPOINTMENTS_PREFIX + k).encode("utf-8")) is None


def test_batch_delete_triggered_appointment_flag(db_manager):
    # Let's add some flags first
    keys = [get_random_value_hex(16) for _ in range(10)]
    db_manager.batch_create_triggered_appointment_flag(keys)

    # And now let's delete in batch
    first_half = keys[: len(keys) // 2]
    second_half = keys[len(keys) // 2 :]

    db_manager.batch_delete_triggered_appointment_flag(first_half)
    db_falgs = db_manager.load_all_triggered_flags()
    assert not set(db_falgs).issuperset(first_half)
    assert set(db_falgs).issuperset(second_half)

    # Delete the rest
    db_manager.batch_delete_triggered_appointment_flag(second_half)
    assert not db_manager.load_all_triggered_flags()
