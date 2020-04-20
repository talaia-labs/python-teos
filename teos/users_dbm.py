import json
import plyvel

from teos import LOG_PREFIX
from teos.db_manager import DBManager

from common.logger import Logger
from common.tools import is_compressed_pk

logger = Logger(actor="UsersDBM", log_name_prefix=LOG_PREFIX)


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
    """

    def __init__(self, db_path):
        if not isinstance(db_path, str):
            raise ValueError("db_path must be a valid path/name")

        try:
            super().__init__(db_path)

        except plyvel.Error as e:
            if "LOCK: Resource temporarily unavailable" in str(e):
                logger.info("The db is already being used by another process (LOCK)")

            raise e

    def store_user(self, user_pk, user_data):
        """
        Stores a user record to the database. ``user_pk`` is used as identifier.

        Args:
            user_pk (:obj:`str`): a 33-byte hex-encoded string identifying the user.
            user_data (:obj:`dict`): the user associated data, as a dictionary.

        Returns:
            :obj:`bool`: True if the user was stored in the database, False otherwise.
        """

        if is_compressed_pk(user_pk):
            try:
                self.create_entry(user_pk, json.dumps(user_data))
                logger.info("Adding user to Gatekeeper's db", user_pk=user_pk)
                return True

            except json.JSONDecodeError:
                logger.info("Could't add user to db. Wrong user data format", user_pk=user_pk, user_data=user_data)
                return False

            except TypeError:
                logger.info("Could't add user to db", user_pk=user_pk, user_data=user_data)
                return False
        else:
            logger.info("Could't add user to db. Wrong pk format", user_pk=user_pk, user_data=user_data)
            return False

    def load_user(self, user_pk):
        """
        Loads a user record from the database using the ``user_pk`` as identifier.

        Args:

            user_pk (:obj:`str`): a 33-byte hex-encoded string identifying the user.

        Returns:
            :obj:`dict`: A dictionary containing the user data if the ``key`` is found.

            Returns ``None`` otherwise.
        """

        try:
            data = self.load_entry(user_pk)
            data = json.loads(data)
        except (TypeError, json.decoder.JSONDecodeError):
            data = None

        return data

    def delete_user(self, user_pk):
        """
        Deletes a user record from the database.

        Args:
           user_pk (:obj:`str`): a 33-byte hex-encoded string identifying the user.

        Returns:
            :obj:`bool`: True if the user was deleted from the database or it was non-existent, False otherwise.
        """

        try:
            self.delete_entry(user_pk)
            logger.info("Deleting user from Gatekeeper's db", uuid=user_pk)
            return True

        except TypeError:
            logger.info("Cannot delete user from db, user key has wrong type", uuid=user_pk)
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
            user_pk = k.decode("utf-8")
            data[user_pk] = json.loads(v)

        return data
