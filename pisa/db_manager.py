import json
import plyvel

from pisa import LOG_PREFIX

from common.logger import Logger

logger = Logger(actor="DBManager", log_name_prefix=LOG_PREFIX)

WATCHER_PREFIX = "w"
WATCHER_LAST_BLOCK_KEY = "bw"
RESPONDER_PREFIX = "r"
RESPONDER_LAST_BLOCK_KEY = "br"
LOCATOR_MAP_PREFIX = "m"
TRIGGERED_APPOINTMENTS_PREFIX = "ta"


class DBManager:
    """
    The :class:`DBManager` is the class in charge of interacting with the appointments database (``LevelDB``).
    Keys and values are stored as bytes in the database but processed as strings by the manager.

    The database is split in six prefixes:

        - ``WATCHER_PREFIX``, defined as ``b'w``, is used to store :obj:`Watcher <pisa.watcher.Watcher>` appointments.
        - ``RESPONDER_PREFIX``, defines as ``b'r``, is used to store :obj:`Responder <pisa.responder.Responder>` trackers.
        - ``WATCHER_LAST_BLOCK_KEY``, defined as ``b'bw``, is used to store the last block hash known by the :obj:`Watcher <pisa.watcher.Watcher>`.
        - ``RESPONDER_LAST_BLOCK_KEY``, defined as ``b'br``, is used to store the last block hash known by the :obj:`Responder <pisa.responder.Responder>`.
        - ``LOCATOR_MAP_PREFIX``, defined as ``b'm``, is used to store the ``locator:uuid`` maps.
        - ``TRIGGERED_APPOINTMENTS_PREFIX``, defined as ``b'ta``, is used to stored triggered appointments (appointments that have been handed to the :obj:`Responder <pisa.responder.Responder>`.)

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

        try:
            self.db = plyvel.DB(db_path)

        except plyvel.Error as e:
            if "create_if_missing is false" in str(e):
                logger.info("No db found. Creating a fresh one")
                self.db = plyvel.DB(db_path, create_if_missing=True)

            elif "LOCK: Resource temporarily unavailable" in str(e):
                logger.info("The db is already being used by another process (LOCK)")
                raise e

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
            include_triggered (:obj:`bool`): Whether to include the appointments flagged as triggered or not. ``False``
                by default.

        Returns:
            :obj:`dict`: A dictionary with all the appointments stored in the database. An empty dictionary is there
            are none.
        """

        appointments = self.load_appointments_db(prefix=WATCHER_PREFIX)
        triggered_appointments = self.load_all_triggered_flags()

        if not include_triggered:
            not_triggered = list(set(appointments.keys()).difference(triggered_appointments))
            appointments = {uuid: appointments[uuid] for uuid in not_triggered}

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

        Args:
            uuid (:obj:`str`): the identifier of the appointment to be stored.
            appointment (:obj: `str`): the json encoded appointment to be stored as data.
        """

        self.create_entry(uuid, appointment, prefix=WATCHER_PREFIX)
        logger.info("Adding appointment to Watchers's db", uuid=uuid)

    def store_responder_tracker(self, uuid, tracker):
        """
        Stores a tracker in the database using the ``RESPONDER_PREFIX`` prefix.

        Args:
            uuid (:obj:`str`): the identifier of the appointment to be stored.
            tracker (:obj: `str`): the json encoded tracker to be stored as data.
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

    def create_append_locator_map(self, locator, uuid):
        """
        Creates (or appends to if already exists) a ``locator:uuid`` map.

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

    def update_locator_map(self, locator, locator_map):
        """
        Updates a ``locator:uuid`` map in the database by deleting one of it's uuid. It will only work as long as
        the given ``locator_map`` is a subset of the current one and it's not empty.

        Args:
            locator (:obj:`str`): a 16-byte hex-encoded string used as the key of the map.
            locator_map (:obj:`list`): a list of uuids to replace the current one on the db.
        """

        current_locator_map = self.load_locator_map(locator)

        if set(locator_map).issubset(current_locator_map) and len(locator_map) is not 0:
            key = (LOCATOR_MAP_PREFIX + locator).encode("utf-8")
            self.db.put(key, json.dumps(locator_map).encode("utf-8"))

        else:
            logger.error("Trying to update a locator_map with completely different, or empty, data")

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

    def batch_delete_watcher_appointments(self, uuids):
        """
        Deletes an appointment from the database.

        Args:
           uuids (:obj:`list`): a list of 16-byte hex-encoded strings identifying the appointments to be deleted.
        """

        with self.db.write_batch() as b:
            for uuid in uuids:
                b.delete((WATCHER_PREFIX + uuid).encode("utf-8"))
                logger.info("Deleting appointment from Watcher's db", uuid=uuid)

    def delete_responder_tracker(self, uuid):
        """
        Deletes a tracker from the database.

        Args:
           uuid (:obj:`str`): a 16-byte hex-encoded string identifying the tracker to be deleted.
        """

        self.delete_entry(uuid, prefix=RESPONDER_PREFIX)
        logger.info("Deleting appointment from Responder's db", uuid=uuid)

    def batch_delete_responder_trackers(self, uuids):
        """
        Deletes an appointment from the database.

        Args:
           uuids (:obj:`list`): a list of 16-byte hex-encoded strings identifying the trackers to be deleted.
        """

        with self.db.write_batch() as b:
            for uuid in uuids:
                b.delete((RESPONDER_PREFIX + uuid).encode("utf-8"))
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

    def create_triggered_appointment_flag(self, uuid):
        """
        Creates a flag that signals that an appointment has been triggered.

        Args:
            uuid (:obj:`str`): the identifier of the flag to be created.
        """

        self.db.put((TRIGGERED_APPOINTMENTS_PREFIX + uuid).encode("utf-8"), "".encode("utf-8"))
        logger.info("Flagging appointment as triggered", uuid=uuid)

    def batch_create_triggered_appointment_flag(self, uuids):
        """
        Creates a flag that signals that an appointment has been triggered for every appointment in the given list

        Args:
            uuids (:obj:`list`): a list of identifier for the appointments to flag.
        """

        with self.db.write_batch() as b:
            for uuid in uuids:
                b.put((TRIGGERED_APPOINTMENTS_PREFIX + uuid).encode("utf-8"), b"")
                logger.info("Flagging appointment as triggered", uuid=uuid)

    def load_all_triggered_flags(self):
        """
        Loads all the appointment triggered flags from the database.

        Returns:
             :obj:`list`: a list of all the uuids of the triggered appointments.
        """

        return [
            k.decode()[len(TRIGGERED_APPOINTMENTS_PREFIX) :]
            for k, v in self.db.iterator(prefix=TRIGGERED_APPOINTMENTS_PREFIX.encode("utf-8"))
        ]

    def delete_triggered_appointment_flag(self, uuid):
        """
        Deletes a flag that signals that an appointment has been triggered.

        Args:
            uuid (:obj:`str`): the identifier of the flag to be removed.
        """

        self.delete_entry(uuid, prefix=TRIGGERED_APPOINTMENTS_PREFIX)
        logger.info("Removing triggered flag from appointment appointment", uuid=uuid)

    def batch_delete_triggered_appointment_flag(self, uuids):
        """
        Deletes a list of flag signaling that some appointment have been triggered.

        Args:
            uuids (:obj:`list`): the identifier of the flag to be removed.
        """

        with self.db.write_batch() as b:
            for uuid in uuids:
                b.delete((TRIGGERED_APPOINTMENTS_PREFIX + uuid).encode("utf-8"))
                logger.info("Removing triggered flag from appointment appointment", uuid=uuid)
