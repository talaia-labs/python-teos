import json
import plyvel

from common.logger import Logger

logger = Logger("DBManager")

WATCHER_PREFIX = "w"
WATCHER_LAST_BLOCK_KEY = "bw"
RESPONDER_PREFIX = "r"
RESPONDER_LAST_BLOCK_KEY = "br"
LOCATOR_MAP_PREFIX = "m"


class DBManager:
    """
    The :class:`DBManager` is the class in charge of interacting with the appointments database (``LevelDB``).
    Keys and values are stored as bytes in the database but processed as strings by the manager.

    The database is split in five prefixes:

        - ``WATCHER_PREFIX``, defined as ``b'w``, is used to store :obj:`Watcher <pisa.watcher.Watcher>` appointments.
        - ``RESPONDER_PREFIX``, defines as ``b'r``, is used to store :obj:`Responder <pisa.responder.Responder>` trackers.
        - ``WATCHER_LAST_BLOCK_KEY``, defined as ``b'bw``, is used to store the last block hash known by the :obj:`Watcher <pisa.watcher.Watcher>`.
        - ``RESPONDER_LAST_BLOCK_KEY``, defined as ``b'br``, is used to store the last block hash known by the :obj:`Responder <pisa.responder.Responder>`.
        - ``LOCATOR_MAP_PREFIX``, defined as ``b'm``, is used to store the ``locator:uuid`` maps.

    Args:
        db_path (:obj:`str`): the path (relative or absolute) to the system folder containing the database. A fresh
            database will be create if the specified path does not contain one.
    """

    def __init__(self, db_path):
        if not isinstance(db_path, str):
            raise ValueError("db_path must be a valid path/name")

        try:
            self.db = plyvel.DB(db_path)

        except plyvel.Error as e:
            if "create_if_missing is false" in str(e):
                logger.info("No db found. Creating a fresh one")
                self.db = plyvel.DB(db_path, create_if_missing=True)

    def load_appointments_db(self, prefix):
        """
        Loads all data from the appointments database given a prefix. Two prefixes are defined: ``WATCHER_PREFIX`` and
        ``RESPONDER_PREFIX``.

        Args:
            prefix (:obj:`str`): the prefix of the data to load.

        Returns:
            :obj:`dict`: A dictionary containing the requested data (appointments or trackers) indexed by ``uuid``.

            Returns an empty dictionary if no data is found.
        """

        data = {}

        for k, v in self.db.iterator(prefix=prefix.encode("utf-8")):
            # Get uuid and appointment_data from the db
            uuid = k[len(prefix) :].decode("utf-8")
            data[uuid] = json.loads(v)

        return data

    def get_last_known_block(self, key):
        """
        Loads the last known block given a key (either ``WATCHER_LAST_BLOCK_KEY`` or ``RESPONDER_LAST_BLOCK_KEY``).

        Returns:
            :obj:`str` or :obj:`None`: A 16-byte hex-encoded str representing the last known block hash.

            Returns ``None`` if the entry is not found.
        """

        last_block = self.db.get(key.encode("utf-8"))

        if last_block:
            last_block = last_block.decode("utf-8")

        return last_block

    def create_entry(self, key, value, prefix=None):
        """
        Creates a new entry in the database.

        Args:
            key (:obj:`str`): the key of the new entry, used to identify it.
            value (:obj:`str`): the data stored under the given ``key``.
            prefix (:obj:`str`): an optional prefix added to the ``key``.
        """

        if isinstance(prefix, str):
            key = prefix + key

        key = key.encode("utf-8")
        value = value.encode("utf-8")

        self.db.put(key, value)

    def load_entry(self, key):
        """
        Loads an entry from the database given a ``key``.

        Args:
            key (:obj:`str`): the key that identifies the entry to be loaded.

        Returns:
            :obj:`dict` or :obj:`None`: A dictionary containing the requested data (an appointment or a tracker).

            Returns ``None`` if the entry is not found.
        """

        data = self.db.get(key.encode("utf-8"))
        data = json.loads(data) if data is not None else data
        return data

    def delete_entry(self, key, prefix=None):
        """
        Deletes an entry from the database given an ``key`` (and optionally a ``prefix``)

        Args:
            key (:obj:`str`): the key that identifies the data to be deleted.
            prefix (:obj:`str`): an optional prefix to be prepended to the ``key``.
        """

        if isinstance(prefix, str):
            key = prefix + key

        key = key.encode("utf-8")

        self.db.delete(key)

    def load_watcher_appointment(self, key):
        """
        Loads an appointment from the database using ``WATCHER_PREFIX`` as prefix to the given ``key``.

        Returns:
            :obj:`dict`: A dictionary containing the appointment data if they ``key`` is found.

            Returns ``None`` otherwise.
        """

        return self.load_entry(WATCHER_PREFIX + key)

    def load_responder_tracker(self, key):
        """
        Loads a tracker from the database using ``RESPONDER_PREFIX`` as a prefix to the given ``key``.

        Returns:
            :obj:`dict`: A dictionary containing the tracker data if they ``key`` is found.

            Returns ``None`` otherwise.
        """

        return self.load_entry(RESPONDER_PREFIX + key)

    def load_watcher_appointments(self, include_triggered=False):
        """
        Loads all the appointments from the database (all entries with the ``WATCHER_PREFIX`` prefix).

        Args:
            include_triggered (:obj:`bool`): Whether to include the appointments flagged as triggered or not. ``False`` by
                default.

        Returns:
            :obj:`dict`: A dictionary with all the appointments stored in the database. An empty dictionary is there
            are none.
        """

        appointments = self.load_appointments_db(prefix=WATCHER_PREFIX)

        if not include_triggered:
            appointments = {
                uuid: appointment for uuid, appointment in appointments.items() if appointment["triggered"] is False
            }

        return appointments

    def load_responder_trackers(self):
        """
        Loads all the trackers from the database (all entries with the ``RESPONDER_PREFIX`` prefix).

        Returns:
            :obj:`dict`: A dictionary with all the trackers stored in the database. An empty dictionary is there are
            none.
        """

        return self.load_appointments_db(prefix=RESPONDER_PREFIX)

    def store_watcher_appointment(self, uuid, appointment):
        """
        Stores an appointment in the database using the ``WATCHER_PREFIX`` prefix.
        """

        self.create_entry(uuid, appointment, prefix=WATCHER_PREFIX)
        logger.info("Adding appointment to Watchers's db", uuid=uuid)

    def store_responder_tracker(self, uuid, tracker):
        """
        Stores a tracker in the database using the ``RESPONDER_PREFIX`` prefix.
        """

        self.create_entry(uuid, tracker, prefix=RESPONDER_PREFIX)
        logger.info("Adding appointment to Responder's db", uuid=uuid)

    def load_locator_map(self, locator):
        """
        Loads the ``locator:uuid`` map of a given ``locator`` from the database.

        Args:
            locator (:obj:`str`): a 16-byte hex-encoded string representing the appointment locator.

        Returns:
            :obj:`dict` or :obj:`None`: The requested ``locator:uuid`` map if found.

            Returns ``None`` otherwise.
        """

        key = (LOCATOR_MAP_PREFIX + locator).encode("utf-8")
        locator_map = self.db.get(key)

        if locator_map is not None:
            locator_map = json.loads(locator_map.decode("utf-8"))

        else:
            logger.info("Locator not found in the db", locator=locator)

        return locator_map

    def store_update_locator_map(self, locator, uuid):
        """
        Stores (or updates if already exists) a ``locator:uuid`` map.

        If the map already exists, the new ``uuid`` is appended to the existing ones (if it is not already there).

        Args:
            locator (:obj:`str`): a 16-byte hex-encoded string used as the key of the map.
            uuid (:obj:`str`): a 16-byte hex-encoded unique id to create (or add to) the map.
        """

        locator_map = self.load_locator_map(locator)

        if locator_map is not None:
            if uuid not in locator_map:
                locator_map.append(uuid)
                logger.info("Updating locator map", locator=locator, uuid=uuid)

            else:
                logger.info("UUID already in the map", locator=locator, uuid=uuid)

        else:
            locator_map = [uuid]
            logger.info("Creating new locator map", locator=locator, uuid=uuid)

        key = (LOCATOR_MAP_PREFIX + locator).encode("utf-8")
        self.db.put(key, json.dumps(locator_map).encode("utf-8"))

    def delete_locator_map(self, locator):
        """
        Deletes a ``locator:uuid`` map.

        Args:
            locator (:obj:`str`): a 16-byte hex-encoded string identifying the map to delete.
        """

        self.delete_entry(locator, prefix=LOCATOR_MAP_PREFIX)
        logger.info("Deleting locator map from db", uuid=locator)

    def delete_watcher_appointment(self, uuid):
        """
        Deletes an appointment from the database.

        Args:
           uuid (:obj:`str`): a 16-byte hex-encoded string identifying the appointment to be deleted.
        """

        self.delete_entry(uuid, prefix=WATCHER_PREFIX)
        logger.info("Deleting appointment from Watcher's db", uuid=uuid)

    def delete_responder_tracker(self, uuid):
        """
        Deletes a tracker from the database.

        Args:
           uuid (:obj:`str`): a 16-byte hex-encoded string identifying the tracker to be deleted.
        """

        self.delete_entry(uuid, prefix=RESPONDER_PREFIX)
        logger.info("Deleting appointment from Responder's db", uuid=uuid)

    def load_last_block_hash_watcher(self):
        """
        Loads the last known block hash of the :obj:`Watcher <pisa.watcher.Watcher>` from the database.

        Returns:
            :obj:`str` or :obj:`None`: A 32-byte hex-encoded string representing the last known block hash if found.

            Returns ``None`` otherwise.
        """
        return self.get_last_known_block(WATCHER_LAST_BLOCK_KEY)

    def load_last_block_hash_responder(self):
        """
        Loads the last known block hash of the :obj:`Responder <pisa.responder.Responder>` from the database.

        Returns:
            :obj:`str` or :obj:`None`: A 32-byte hex-encoded string representing the last known block hash if found.

            Returns ``None`` otherwise.
        """
        return self.get_last_known_block(RESPONDER_LAST_BLOCK_KEY)

    def store_last_block_hash_watcher(self, block_hash):
        """
        Stores a block hash as the last known block of the :obj:`Watcher <pisa.watcher.Watcher>`.

        Args:
            block_hash (:obj:`str`): the block hash to be stored (32-byte hex-encoded)
        """

        self.create_entry(WATCHER_LAST_BLOCK_KEY, block_hash)

    def store_last_block_hash_responder(self, block_hash):
        """
        Stores a block hash as the last known block of the :obj:`Responder <pisa.responder.Responder>`.

        Args:
            block_hash (:obj:`str`): the block hash to be stored (32-byte hex-encoded)
        """

        self.create_entry(RESPONDER_LAST_BLOCK_KEY, block_hash)
