import os
import shutil
import pytest

from common.db_manager import DBManager
from test.common.unit.conftest import get_random_value_hex


def open_create_db(db_path):

    try:
        db_manager = DBManager(db_path)

        return db_manager

    except ValueError:
        return False


def test_init():
    db_path = "init_test_db"

    # First we check if the db exists, and if so we delete it
    if os.path.isdir(db_path):
        shutil.rmtree(db_path)

    # Check that the db can be created if it does not exist
    db_manager = open_create_db(db_path)
    assert isinstance(db_manager, DBManager)
    db_manager.db.close()

    # Check that we can open an already create db
    db_manager = open_create_db(db_path)
    assert isinstance(db_manager, DBManager)
    db_manager.db.close()

    # Check we cannot create/open a db with an invalid parameter
    assert open_create_db(0) is False

    # Removing test db
    shutil.rmtree(db_path)


def test_create_entry(db_manager):
    key = get_random_value_hex(16)
    value = get_random_value_hex(32)

    # Adding a value with no prefix should work
    db_manager.create_entry(key, value)
    assert db_manager.db.get(key.encode("utf-8")).decode("utf-8") == value

    # Prefixing the key would require the prefix to load
    key = get_random_value_hex(16)
    prefix = "w"
    db_manager.create_entry(key, value, prefix=prefix)

    assert db_manager.db.get((prefix + key).encode("utf-8")).decode("utf-8") == value
    assert db_manager.db.get(key.encode("utf-8")) is None

    # Keys, prefixes, and values of wrong format should fail
    with pytest.raises(TypeError):
        db_manager.create_entry(key=None)

    with pytest.raises(TypeError):
        db_manager.create_entry(key=key, value=None)

    with pytest.raises(TypeError):
        db_manager.create_entry(key=key, value=value, prefix=1)


def test_load_entry(db_manager):
    key = get_random_value_hex(16)
    value = get_random_value_hex(32)

    # Loading an existing key should work
    db_manager.db.put(key.encode("utf-8"), value.encode("utf-8"))
    assert db_manager.load_entry(key) == value.encode("utf-8")

    # Adding an existing prefix should work
    assert db_manager.load_entry(key[2:], prefix=key[:2]) == value.encode("utf-8")

    # Adding a non-existing prefix should return None
    assert db_manager.load_entry(key, prefix=get_random_value_hex(2)) is None

    # Loading a non-existing entry should return None
    assert db_manager.load_entry(get_random_value_hex(16)) is None

    # Trying to load a non str key or prefix should fail
    with pytest.raises(TypeError):
        db_manager.load_entry(None)

    with pytest.raises(TypeError):
        db_manager.load_entry(get_random_value_hex(16), prefix=1)


def test_delete_entry(db_manager):
    # Let's get the key all the things we've wrote so far in the db and empty the db.
    data = [k.decode("utf-8") for k, v in db_manager.db.iterator()]
    for key in data:
        db_manager.delete_entry(key)

    assert len([k for k, v in db_manager.db.iterator()]) == 0

    # The same works if a prefix is provided.
    prefix = "r"
    key = get_random_value_hex(16)
    value = get_random_value_hex(32)
    db_manager.create_entry(key, value, prefix)

    # Checks it's there
    assert db_manager.db.get((prefix + key).encode("utf-8")).decode("utf-8") == value

    # And now it's gone
    db_manager.delete_entry(key, prefix)
    assert db_manager.db.get((prefix + key).encode("utf-8")) is None

    # Deleting a non-existing key should be fine
    db_manager.delete_entry(key, prefix)

    # Trying to delete a non str key or prefix should fail
    with pytest.raises(TypeError):
        db_manager.delete_entry(None)

    with pytest.raises(TypeError):
        db_manager.delete_entry(get_random_value_hex(16), prefix=1)
