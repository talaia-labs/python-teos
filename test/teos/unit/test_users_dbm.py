import pytest
import shutil
from teos.users_dbm import UsersDBM
from teos.gatekeeper import UserInfo

from test.teos.unit.conftest import get_random_value_hex


@pytest.fixture
def user_db_manager(db_name="test_user_db"):
    manager = UsersDBM(db_name)

    yield manager

    manager.db.close()
    shutil.rmtree(db_name)


def test_store_user(user_db_manager):
    # Tests that users can be properly stored in the database

    # Store user should work as long as the user_pk is properly formatted and data is a dictionary
    user_id = "02" + get_random_value_hex(32)
    user_info = UserInfo(available_slots=42, subscription_expiry=100)

    assert user_db_manager.store_user(user_id, user_info.to_dict()) is True


def test_store_user_wrong(user_db_manager):
    # Tests that trying to store wrong data will fail

    # Wrong pks should return False on adding
    user_id = "04" + get_random_value_hex(32)
    user_info = UserInfo(available_slots=42, subscription_expiry=100)
    assert user_db_manager.store_user(user_id, user_info.to_dict()) is False

    # Same for wrong types
    assert user_db_manager.store_user(42, user_info.to_dict()) is False

    # And for wrong type user data
    assert user_db_manager.store_user(user_id, 42) is False


def test_load_user(user_db_manager):
    # Tests that loading a user should work, as long as the user is there

    # Add the user first
    user_id = "02" + get_random_value_hex(32)
    user_info = UserInfo(available_slots=42, subscription_expiry=100)
    user_db_manager.store_user(user_id, user_info.to_dict())

    # Now load it
    assert user_db_manager.load_user(user_id) == user_info.to_dict()


def test_load_user_wrong(user_db_manager):
    # Tests that wrong data won't load

    # Random keys should fail
    assert user_db_manager.load_user(get_random_value_hex(33)) is None

    # Wrong format keys should also return None
    assert user_db_manager.load_user(42) is None


def test_delete_user(user_db_manager):
    # Tests that deleting existing users should work
    stored_users = {}

    # Add some users first
    for _ in range(10):
        user_id = "02" + get_random_value_hex(32)
        user_info = UserInfo(available_slots=42, subscription_expiry=100)
        user_db_manager.store_user(user_id, user_info.to_dict())
        stored_users[user_id] = user_info

    # Deleting existing users should work
    for user_id, user_data in stored_users.items():
        assert user_db_manager.delete_user(user_id) is True

    # There should be no users anymore
    assert not user_db_manager.load_all_users()


def test_delete_user_wrong(user_db_manager):
    # Tests that deleting users with wrong data should fail

    # Non-existing user
    assert user_db_manager.delete_user(get_random_value_hex(32)) is True

    # Keys of wrong type
    assert user_db_manager.delete_user(42) is False


def test_load_all_users(user_db_manager):
    # Tests loading all the users in the database
    stored_users = {}

    # There should be no users at the moment
    assert user_db_manager.load_all_users() == {}
    stored_users = {}

    # Adding some and checking we get them all
    for i in range(10):
        user_id = "02" + get_random_value_hex(32)
        user_info = UserInfo(available_slots=42, subscription_expiry=100)
        user_db_manager.store_user(user_id, user_info.to_dict())
        stored_users[user_id] = user_info.to_dict()

    all_users = user_db_manager.load_all_users()
    assert all_users == stored_users
