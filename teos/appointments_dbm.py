import json
import plyvel

from teos.logger import get_logger
from common.db_manager import DBManager

WATCHER_PREFIX = "w"
WATCHER_LAST_BLOCK_KEY = "bw"
RESPONDER_PREFIX = "r"
RESPONDER_LAST_BLOCK_KEY = "br"
TRIGGERED_APPOINTMENTS_PREFIX = "ta"


class AppointmentsDBM(DBManager):
    """
    The :class:`AppointmentsDBM` is in charge of interacting with the appointments database (``LevelDB``).
    Keys and values are stored as bytes in the database but processed as strings by the manager.

    The database is split in six prefixes:

        - ``WATCHER_PREFIX``, defined as ``b'w``, is used to store :obj:`Watcher <teos.watcher.Watcher>` appointments.
        - ``RESPONDER_PREFIX``, defines as ``b'r``, is used to store :obj:`Responder <teos.responder.Responder>` trackers.
        - ``WATCHER_LAST_BLOCK_KEY``, defined as ``b'bw``, is used to store the last block hash known by the :obj:`Watcher <teos.watcher.Watcher>`.
        - ``RESPONDER_LAST_BLOCK_KEY``, defined as ``b'br``, is used to store the last block hash known by the :obj:`Responder <teos.responder.Responder>`.
        - ``TRIGGERED_APPOINTMENTS_PREFIX``, defined as ``b'ta``, is used to stored triggered appointments (appointments that have been handed to the :obj:`Responder <teos.responder.Responder>`.)

    Args:
        db_path (:obj:`str`): the path (relative or absolute) to the system folder containing the database. A fresh
            database will be created if the specified path does not contain one.
   
    Attributes:
        logger (:obj:`Logger <teos.logger.Logger>`): the logger for this component.

    Raises:
        :obj:`ValueError`: If the provided ``db_path`` is not a string.
        :obj:`plyvel.Error`: If the db is currently unavailable (being used by another process).
    """  # noqa: E501

    def __init__(self, db_path):
        if not isinstance(db_path, str):
            raise ValueError("db_path must be a valid path/name")

        self.logger = get_logger(component=AppointmentsDBM.__name__)

        try:
            super().__init__(db_path)

        except plyvel.Error as e:
            if "LOCK: Resource temporarily unavailable" in str(e):
                self.logger.info("The db is already being used by another process (LOCK)")

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

        try:
            for k, v in self.db.iterator(prefix=prefix.encode("utf-8")):
                # Get uuid and appointment_data from the db
                uuid = k[len(prefix) :].decode("utf-8")  # noqa: E203
                data[uuid] = json.loads(v)

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

        return data

    def get_last_known_block(self, key):
        """
        Loads the last known block given a key.

        Args:
            key (:obj:`str`): the identifier of the db to look into (either ``WATCHER_LAST_BLOCK_KEY`` or
                ``RESPONDER_LAST_BLOCK_KEY``).

        Returns:
            :obj:`str` or :obj:`None`: A 32-byte hex-encoded str representing the last known block hash.

            Returns :obj:`None` if the entry is not found.
        """

        try:
            last_block = self.db.get(key.encode("utf-8"))

            if last_block:
                last_block = last_block.decode("utf-8")
        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

        return last_block

    def load_watcher_appointment(self, uuid):
        """
        Loads an appointment from the database using ``WATCHER_PREFIX`` as prefix to the given ``uuid``.

        Args:
            uuid (:obj:`str`): the appointment's unique identifier.

        Returns:
            :obj:`dict`: A dictionary containing the appointment data if they ``key`` is found.

            Returns :obj:`None` otherwise.
        """

        try:
            data = self.load_entry(uuid, prefix=WATCHER_PREFIX)
            data = json.loads(data)
        except (TypeError, json.decoder.JSONDecodeError) as e:
            self.logger.error(str(e))
            data = None

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

        return data

    def load_responder_tracker(self, uuid):
        """
        Loads a tracker from the database using ``RESPONDER_PREFIX`` as a prefix to the given ``uuid``.

        Args:
            uuid (:obj:`str`): the tracker's unique identifier.

        Returns:
            :obj:`dict`: A dictionary containing the tracker data if they ``key`` is found.

            Returns :obj:`None` otherwise.
        """

        try:
            data = self.load_entry(uuid, prefix=RESPONDER_PREFIX)
            data = json.loads(data)
        except (TypeError, json.decoder.JSONDecodeError) as e:
            self.logger.error(str(e))
            data = None

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

        return data

    def load_watcher_appointments(self, include_triggered=False):
        """
        Loads all the appointments from the database (all entries with the ``WATCHER_PREFIX`` prefix).

        Args:
            include_triggered (:obj:`bool`): whether to include the appointments flagged as triggered or not. False
                by default.

        Returns:
            :obj:`dict`: A dictionary with all the appointments stored in the database. An empty dictionary if there
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
            :obj:`dict`: A dictionary with all the trackers stored in the database. An empty dictionary if there are
            none.
        """

        return self.load_appointments_db(prefix=RESPONDER_PREFIX)

    def store_watcher_appointment(self, uuid, appointment):
        """
        Stores an appointment in the database using the ``WATCHER_PREFIX`` prefix.

        Args:
            uuid (:obj:`str`): the identifier of the appointment to be stored.
            appointment (:obj:`dict`): an appointment encoded as a dictionary.

        Returns:
            :obj:`bool`: True if the appointment was stored in the db. False otherwise.
        """

        try:
            self.logger.info("Adding appointment to Watchers's db", uuid=uuid)
            self.create_entry(uuid, json.dumps(appointment), prefix=WATCHER_PREFIX)
            return True

        except json.JSONDecodeError:
            self.logger.info(
                "Couldn't add appointment to db. Wrong appointment format.", uuid=uuid, appointment=appointment
            )
            return False

        except TypeError:
            self.logger.info("Couldn't add appointment to db.", uuid=uuid, appointment=appointment)
            return False

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def store_responder_tracker(self, uuid, tracker):
        """
        Stores a tracker in the database using the ``RESPONDER_PREFIX`` prefix.

        Args:
            uuid (:obj:`str`): the identifier of the appointment to be stored.
            tracker (:obj:`dict`): a tracker encoded as a dictionary.

        Returns:
            :obj:`bool`: True if the tracker was stored in the db. False otherwise.
        """

        try:
            self.logger.info("Adding tracker to Responder's db", uuid=uuid)
            self.create_entry(uuid, json.dumps(tracker), prefix=RESPONDER_PREFIX)
            return True

        except json.JSONDecodeError:
            self.logger.info("Couldn't add tracker to db. Wrong tracker format.", uuid=uuid, tracker=tracker)
            return False

        except TypeError:
            self.logger.info("Couldn't add tracker to db.", uuid=uuid, tracker=tracker)
            return False

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def delete_watcher_appointment(self, uuid):
        """
        Deletes an appointment from the database.

        Args:
           uuid (:obj:`str`): a 16-byte hex-encoded string identifying the appointment to be deleted.

        Returns:
            :obj:`bool`: True if the appointment was deleted from the database or it was non-existent, False otherwise.
        """

        try:
            self.logger.info("Deleting appointment from Watcher's db", uuid=uuid)
            self.delete_entry(uuid, prefix=WATCHER_PREFIX)
            return True

        except TypeError:
            self.logger.info("Couldn't delete appointment from db, uuid has wrong type", uuid=uuid)
            return False

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def batch_delete_watcher_appointments(self, uuids):
        """
        Deletes multiple appointments from the database.

        Args:
           uuids (:obj:`list`): a list of 16-byte hex-encoded strings identifying the appointments to be deleted.
        """

        try:
            with self.db.write_batch() as b:
                for uuid in uuids:
                    self.logger.info("Deleting appointment from Watcher's db", uuid=uuid)
                    b.delete((WATCHER_PREFIX + uuid).encode("utf-8"))

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def delete_responder_tracker(self, uuid):
        """
        Deletes a tracker from the database.

        Args:
           uuid (:obj:`str`): a 16-byte hex-encoded string identifying the tracker to be deleted.

        Returns:
            :obj:`bool`: True if the tracker was deleted from the database or it was non-existent, False otherwise.
        """

        try:
            self.logger.info("Deleting tracker from Responder's db", uuid=uuid)
            self.delete_entry(uuid, prefix=RESPONDER_PREFIX)
            return True

        except TypeError:
            self.logger.info("Couldn't delete tracker from db, uuid has wrong type", uuid=uuid)
            return False

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def batch_delete_responder_trackers(self, uuids):
        """
        Deletes multiple trackers from the database.

        Args:
           uuids (:obj:`list`): a list of 16-byte hex-encoded strings identifying the trackers to be deleted.
        """

        try:
            with self.db.write_batch() as b:
                for uuid in uuids:
                    self.logger.info("Deleting appointment from Responder's db", uuid=uuid)
                    b.delete((RESPONDER_PREFIX + uuid).encode("utf-8"))
        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def load_last_block_hash_watcher(self):
        """
        Loads the last known block hash of the :obj:`Watcher <teos.watcher.Watcher>` from the database.

        Returns:
            :obj:`str` or :obj:`None`: A 32-byte hex-encoded string representing the last known block hash if found.

            Returns :obj:`None` otherwise.
        """
        return self.get_last_known_block(WATCHER_LAST_BLOCK_KEY)

    def load_last_block_hash_responder(self):
        """
        Loads the last known block hash of the :obj:`Responder <teos.responder.Responder>` from the database.

        Returns:
            :obj:`str` or :obj:`None`: A 32-byte hex-encoded string representing the last known block hash if found.

            Returns :obj:`None` otherwise.
        """
        return self.get_last_known_block(RESPONDER_LAST_BLOCK_KEY)

    def store_last_block_hash_watcher(self, block_hash):
        """
        Stores a block hash as the last known block of the :obj:`Watcher <teos.watcher.Watcher>`.

        Args:
            block_hash (:obj:`str`): the block hash to be stored (32-byte hex-encoded)

        Returns:
            :obj:`bool`: True if the block hash was stored in the db. False otherwise.
        """

        try:
            self.create_entry(WATCHER_LAST_BLOCK_KEY, block_hash)
            return True

        except (TypeError, json.JSONDecodeError) as e:
            self.logger.error(str(e))
            return False

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def store_last_block_hash_responder(self, block_hash):
        """
        Stores a block hash as the last known block of the :obj:`Responder <teos.responder.Responder>`.

        Args:
            block_hash (:obj:`str`): the block hash to be stored (32-byte hex-encoded)

        Returns:
            :obj:`bool`: True if the block hash was stored in the db. False otherwise.
        """

        try:
            self.create_entry(RESPONDER_LAST_BLOCK_KEY, block_hash)
            return True

        except (TypeError, json.JSONDecodeError) as e:
            self.logger.error(str(e))
            return False

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def create_triggered_appointment_flag(self, uuid):
        """
        Creates a flag that signals that an appointment has been triggered.

        Args:
            uuid (:obj:`str`): the identifier of the flag to be created.
        """

        try:
            self.logger.info("Flagging appointment as triggered", uuid=uuid)
            self.db.put((TRIGGERED_APPOINTMENTS_PREFIX + uuid).encode("utf-8"), "".encode("utf-8"))
        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def batch_create_triggered_appointment_flag(self, uuids):
        """
        Creates a flag that signals that an appointment has been triggered for every appointment in the given list.

        Args:
            uuids (:obj:`list`): a list of identifiers for the appointments to flag.
        """

        try:
            with self.db.write_batch() as b:
                for uuid in uuids:
                    self.logger.info("Flagging appointment as triggered", uuid=uuid)
                    b.put((TRIGGERED_APPOINTMENTS_PREFIX + uuid).encode("utf-8"), b"")
        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def load_all_triggered_flags(self):
        """
        Loads all the appointment triggered flags from the database.

        Returns:
             :obj:`list`: a list of all the uuids of the triggered appointments.
        """

        try:
            return [
                k.decode()[len(TRIGGERED_APPOINTMENTS_PREFIX) :]  # noqa: E203
                for k, v in self.db.iterator(prefix=TRIGGERED_APPOINTMENTS_PREFIX.encode("utf-8"))
            ]
        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def delete_triggered_appointment_flag(self, uuid):
        """
        Deletes a flag that signals that an appointment has been triggered.

        Args:
            uuid (:obj:`str`): the identifier of the flag to be removed.

        Returns:
            :obj:`bool`: True if the flag was deleted from the database or it was non-existent, False otherwise.
        """

        try:
            self.logger.info("Removing triggered flag from appointment appointment", uuid=uuid)
            self.delete_entry(uuid, prefix=TRIGGERED_APPOINTMENTS_PREFIX)
            return True

        except TypeError:
            self.logger.info("Couldn't delete triggered flag from db, uuid has wrong type", uuid=uuid)
            return False

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e

    def batch_delete_triggered_appointment_flag(self, uuids):
        """
        Deletes a list of flag signaling that some appointment have been triggered.

        Args:
            uuids (:obj:`list`): the identifier of the flag to be removed.
        """

        try:
            with self.db.write_batch() as b:
                for uuid in uuids:
                    self.logger.info("Removing triggered flag from appointment appointment", uuid=uuid)
                    b.delete((TRIGGERED_APPOINTMENTS_PREFIX + uuid).encode("utf-8"))

        except RuntimeError as e:
            self.logger.error(str(e))
            raise e
