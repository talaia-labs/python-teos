import plyvel


class DBManager:
    """
    The :class:`DBManager` is in charge of interacting with a database (``LevelDB``).
    Keys and values are stored as bytes in the database but processed as strings by the manager.

    Args:
        db_path (:obj:`str`): the path (relative or absolute) to the system folder containing the database. A fresh
            database will be create if the specified path does not contain one.

    Raises:
        ValueError: If the provided ``db_path`` is not a string.
        plyvel.Error: If the db is currently unavailable (being used by another process).
    """

    def __init__(self, db_path):
        if not isinstance(db_path, str):
            raise ValueError("db_path must be a valid path/name")

        self.db = plyvel.DB(db_path, create_if_missing=True)

    def create_entry(self, key, value, prefix=None):
        """
        Creates a new entry in the database.

        Args:
            key (:obj:`str`): the key of the new entry, used to identify it.
            value (:obj:`str`): the data stored under the given ``key``.
            prefix (:obj:`str`): an optional prefix added to the ``key``.

        Raises:
            (:obj:`TypeError`) if key, value or prefix are not strings.
        """

        if not isinstance(key, str):
            raise TypeError("Key must be str")

        if not isinstance(value, str):
            raise TypeError("Value must be str")

        if not isinstance(prefix, str) and prefix is not None:
            raise TypeError("Prefix (if set) must be str")

        if isinstance(prefix, str):
            key = prefix + key

        key = key.encode("utf-8")
        value = value.encode("utf-8")

        self.db.put(key, value)

    def load_entry(self, key, prefix=None):
        """
        Loads an entry from the database given a ``key`` (and optionally a ``prefix``).

        Args:
            key (:obj:`str`): the key that identifies the entry to be loaded.
            prefix (:obj:`str`): an optional prefix added to the ``key``.

        Returns:
            :obj:`bytes` or :obj:`None`: A byte-array containing the requested data.

            Returns ``None`` if the entry is not found.

        Raises:
            (:obj:`TypeError`) if key or prefix are not strings.
        """

        if not isinstance(key, str):
            raise TypeError("Key must be str")

        if not isinstance(prefix, str) and prefix is not None:
            raise TypeError("Prefix (if set) must be str")

        if isinstance(prefix, str):
            key = prefix + key

        return self.db.get(key.encode("utf-8"))

    def delete_entry(self, key, prefix=None):
        """
        Deletes an entry from the database given an ``key`` (and optionally a ``prefix``).

        Args:
            key (:obj:`str`): the key that identifies the data to be deleted.
            prefix (:obj:`str`): an optional prefix to be prepended to the ``key``.

        Raises:
            (:obj:`TypeError`) if key or prefix are not strings.
        """

        if not isinstance(key, str):
            raise TypeError("Key must be str")

        if not isinstance(prefix, str) and prefix is not None:
            raise TypeError("Prefix (if set) must be str")

        if isinstance(prefix, str):
            key = prefix + key

        key = key.encode("utf-8")

        self.db.delete(key)
