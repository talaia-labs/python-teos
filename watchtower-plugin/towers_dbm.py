import json

from common.db_manager import DBManager
from common.tools import is_compressed_pk


class TowersDBM(DBManager):
    """
    The :class:`TowersDBM` is in charge of interacting with the towers database (``LevelDB``).
    Keys and values are stored as bytes in the database but processed as strings by the manager.

    Args:
        db_path (:obj:`str`): the path (relative or absolute) to the system folder containing the database. A fresh
            database will be created if the specified path does not contain one.

    Raises:
        :obj:`ValueError`: If the provided ``db_path`` is not a string.
        :obj:`plyvel.Error`: If the db is currently unavailable (being used by another process).
    """

    def __init__(self, db_path, plugin):
        if not isinstance(db_path, str):
            raise ValueError("db_path must be a valid path/name")

        super().__init__(db_path)
        self.plugin = plugin

    def store_tower_record(self, tower_id, tower_data):
        """
        Stores a tower record to the database. ``tower_id`` is used as identifier.

        Args:
            tower_id (:obj:`str`): a 33-byte hex-encoded string identifying the tower.
            tower_data (:obj:`dict`): the tower associated data, as a dictionary.

        Returns:
            :obj:`bool`: True if the tower record was stored in the database, False otherwise.
        """

        if is_compressed_pk(tower_id):
            try:
                self.create_entry(tower_id, json.dumps(tower_data.to_dict()))
                self.plugin.log("Adding tower to Tower's db (id={})".format(tower_id))
                return True

            except (json.JSONDecodeError, TypeError):
                self.plugin.log(
                    "Could't add tower to db. Wrong tower data format (tower_id={}, tower_data={})".format(
                        tower_id, tower_data
                    )
                )
                return False

        else:
            self.plugin.log(
                "Could't add user to db. Wrong pk format (tower_id={}, tower_data={})".format(tower_id, tower_data)
            )
            return False

    def load_tower_record(self, tower_id):
        """
        Loads a tower record from the database using the ``tower_id`` as identifier.

        Args:

            tower_id (:obj:`str`): a 33-byte hex-encoded string identifying the tower.

        Returns:
            :obj:`dict`: A dictionary containing the tower data if the ``key`` is found.

            Returns ``None`` otherwise.
        """

        try:
            data = self.load_entry(tower_id)
            data = json.loads(data)
        except (TypeError, json.decoder.JSONDecodeError):
            data = None

        return data

    def delete_tower_record(self, tower_id):
        """
        Deletes a tower record from the database.

        Args:
           tower_id (:obj:`str`): a 33-byte hex-encoded string identifying the tower.

        Returns:
            :obj:`bool`: True if the tower was deleted from the database or it was non-existent, False otherwise.
        """

        try:
            self.delete_entry(tower_id)
            self.plugin.log("Deleting tower from Tower's db (id={})".format(tower_id))
            return True

        except TypeError:
            self.plugin.log("Cannot delete user from db, user key has wrong type (id={})".format(tower_id))
            return False

    def load_all_tower_records(self):
        """
        Loads all tower records from the database.

        Returns:
            :obj:`dict`: A dictionary containing all tower records indexed by ``tower_id``.

            Returns an empty dictionary if no data is found.
        """

        data = {}

        for k, v in self.db.iterator():
            # Get uuid and appointment_data from the db
            tower_id = k.decode("utf-8")
            data[tower_id] = json.loads(v)

        return data
