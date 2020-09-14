import json
import plyvel

from teos.logger import get_logger
from common.db_manager import DBManager
from common.tools import is_compressed_pk


class UsersDBM(DBManager):
    """
    The :class:`UsersDBM` is in charge of interacting with the users database (``LevelDB``).
    Keys and values are stored as bytes in the database but processed as strings by the manager.

    Args:
        db_path (:obj:`str`): the path (relative or absolute) to the system folder containing the database. A fresh
            database will be created if the specified path does not contain one.

    Raises:
        :obj:`ValueError`: If the provided ``db_path`` is not a string.
        :obj:`plyvel.Error`: If the db is currently unavailable (being used by another process).

    Attributes:
        logger (:obj:`Logger <teos.logger.Logger>`): The logger for this component.
    """

    def __init__(self, db_path):
        self.logger = get_logger(component=UsersDBM.__name__)

        if not isinstance(db_path, str):
            raise ValueError("db_path must be a valid path/name")

        try:
            super().__init__(db_path)

        except plyvel.Error as e:
            if "LOCK: Resource temporarily unavailable" in str(e):
                self.logger.info("The db is already being used by another process (LOCK)")

            raise e

    def store_user(self, user_id, user_data):
        """
        Stores a user record to the database. ``user_pk`` is used as identifier.

        Args:
            user_id (:obj:`str`): a 33-byte hex-encoded string identifying the user.
            user_data (:obj:`dict`): the user associated data, as a dictionary.

        Returns:
            :obj:`bool`: True if the user was stored in the database, False otherwise.
        """

        if is_compressed_pk(user_id):
            try:
                self.create_entry(user_id, json.dumps(user_data))
                self.logger.info("Adding user to Gatekeeper's db", user_id=user_id)
                return True

            except json.JSONDecodeError:
                self.logger.info(
                    "Couldn't add user to db. Wrong user data format", user_id=user_id, user_data=user_data
                )
                return False

            except TypeError:
                self.logger.info("Couldn't add user to db", user_id=user_id, user_data=user_data)
                return False
        else:
            self.logger.info("Couldn't add user to db. Wrong pk format", user_id=user_id, user_data=user_data)
            return False

    def load_user(self, user_id):
        """
        Loads a user record from the database using the ``user_pk`` as identifier.

        Args:

            user_id (:obj:`str`): a 33-byte hex-encoded string identifying the user.

        Returns:
            :obj:`dict`: A dictionary containing the user data if the ``key`` is found.

            Returns :obj:`None` otherwise.
        """

        try:
            data = self.load_entry(user_id)
            data = json.loads(data)
        except (TypeError, json.decoder.JSONDecodeError):
            data = None

        return data

    def delete_user(self, user_id):
        """
        Deletes a user record from the database.

        Args:
           user_id (:obj:`str`): a 33-byte hex-encoded string identifying the user.

        Returns:
            :obj:`bool`: True if the user was deleted from the database or it was non-existent, False otherwise.
        """

        try:
            self.delete_entry(user_id)
            self.logger.info("Deleting user from Gatekeeper's db", uuid=user_id)
            return True

        except TypeError:
            self.logger.info("Cannot delete user from db, user key has wrong type", uuid=user_id)
            return False

    def load_all_users(self):
        """
        Loads all user records from the database.

        Returns:
            :obj:`dict`: A dictionary containing all users indexed by ``user_pk``.

            Returns an empty dictionary if no data is found.
        """

        data = {}

        for k, v in self.db.iterator():
            # Get uuid and appointment_data from the db
            user_id = k.decode("utf-8")
            data[user_id] = json.loads(v)

        return data
