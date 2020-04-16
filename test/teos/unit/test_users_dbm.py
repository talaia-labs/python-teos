from teos.users_dbm import UsersDBM
from teos.gatekeeper import UserInfo

from test.teos.unit.conftest import get_random_value_hex

stored_users = {}


def open_create_db(db_path):

    try:
        db_manager = UsersDBM(db_path)

        return db_manager

    except ValueError:
        return False


def test_store_user(user_db_manager):
    # Store user should work as long as the user_pk is properly formatted and data is a dictionary
    user_pk = "02" + get_random_value_hex(32)
    user_info = UserInfo(available_slots=42, subscription_expiry=100)
    stored_users[user_pk] = user_info.to_dict()
    assert user_db_manager.store_user(user_pk, user_info.to_dict()) is True

    # Wrong pks should return False on adding
    user_pk = "04" + get_random_value_hex(32)
    user_info = UserInfo(available_slots=42, subscription_expiry=100)
    assert user_db_manager.store_user(user_pk, user_info.to_dict()) is False

    # Same for wrong types
    assert user_db_manager.store_user(42, user_info.to_dict()) is False

    # And for wrong type user data
    assert user_db_manager.store_user(user_pk, 42) is False


def test_load_user(user_db_manager):
    # Loading a user we have stored should work
    for user_pk, user_data in stored_users.items():
        assert user_db_manager.load_user(user_pk) == user_data

    # Random keys should fail
    assert user_db_manager.load_user(get_random_value_hex(33)) is None

    # Wrong format keys should also return None
    assert user_db_manager.load_user(42) is None


def test_delete_user(user_db_manager):
    # Deleting an existing user should work
    for user_pk, user_data in stored_users.items():
        assert user_db_manager.delete_user(user_pk) is True

    for user_pk, user_data in stored_users.items():
        assert user_db_manager.load_user(user_pk) is None

    # But deleting a non existing one should not fail
    assert user_db_manager.delete_user(get_random_value_hex(32)) is True

    # Keys of wrong type should fail
    assert user_db_manager.delete_user(42) is False


def test_load_all_users(user_db_manager):
    # There should be no users at the moment
    assert user_db_manager.load_all_users() == {}
    stored_users = {}

    # Adding some and checking we get them all
    for i in range(10):
        user_pk = "02" + get_random_value_hex(32)
        user_info = UserInfo(available_slots=42, subscription_expiry=100)
        user_db_manager.store_user(user_pk, user_info.to_dict())
        stored_users[user_pk] = user_info.to_dict()

    all_users = user_db_manager.load_all_users()

    assert set(all_users.keys()) == set(stored_users.keys())
    for k, v in all_users.items():
        assert stored_users[k] == v
