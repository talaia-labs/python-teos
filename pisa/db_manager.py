import json
import plyvel

from pisa.logger import Logger

logger = Logger("DBManager")

WATCHER_PREFIX = "w"
WATCHER_LAST_BLOCK_KEY = "bw"
RESPONDER_PREFIX = "r"
RESPONDER_LAST_BLOCK_KEY = "br"
LOCATOR_MAP_PREFIX = 'm'


class DBManager:
    def __init__(self, db_path):
        if not isinstance(db_path, str):
            raise ValueError("db_path must be a valid path/name")

        try:
            self.db = plyvel.DB(db_path)

        except plyvel.Error as e:
            if 'create_if_missing is false' in str(e):
                logger.info("No db found. Creating a fresh one")
                self.db = plyvel.DB(db_path, create_if_missing=True)

    def load_appointments_db(self, prefix):
        data = {}

        for k, v in self.db.iterator(prefix=prefix.encode('utf-8')):
            # Get uuid and appointment_data from the db
            uuid = k[len(prefix):].decode('utf-8')
            data[uuid] = json.loads(v)

        return data

    def get_last_known_block(self, key):
        last_block = self.db.get(key.encode('utf-8'))

        if last_block:
            last_block = last_block.decode('utf-8')

        return last_block

    def create_entry(self, key, value, prefix=None):
        if isinstance(prefix, str):
            key = prefix + key

        key = key.encode('utf-8')
        value = value.encode('utf-8')

        self.db.put(key, value)

    def delete_entry(self, key,  prefix=None):
        if isinstance(prefix, str):
            key = prefix + key

        key = key.encode('utf-8')

        self.db.delete(key)

    def load_watcher_appointments(self):
        all_appointments = self.load_appointments_db(prefix=WATCHER_PREFIX)
        non_triggered_appointments = {uuid: appointment for uuid, appointment in all_appointments.items()
                                      if appointment["triggered"] is False}

        return non_triggered_appointments

    def load_responder_jobs(self):
        return self.load_appointments_db(prefix=RESPONDER_PREFIX)

    def store_watcher_appointment(self, uuid, appointment):
        self.create_entry(uuid, appointment, prefix=WATCHER_PREFIX)
        logger.info("Adding appointment to Watchers's db", uuid=uuid)

    def store_responder_job(self, uuid, job):
        self.create_entry(uuid, job, prefix=RESPONDER_PREFIX)
        logger.info("Adding appointment to Responder's db", uuid=uuid)

    def load_locator_map(self, locator):
        key = (LOCATOR_MAP_PREFIX+locator).encode('utf-8')
        locator_map = self.db.get(key)

        if locator_map is not None:
            locator_map = json.loads(locator_map.decode('utf-8'))

        else:
            logger.info("Locator not found in the db", locator=locator)

        return locator_map

    def store_update_locator_map(self, locator, uuid):
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

        key = (LOCATOR_MAP_PREFIX + locator).encode('utf-8')
        self.db.put(key, json.dumps(locator_map).encode('utf-8'))

    def delete_locator_map(self, locator):
        self.delete_entry(locator, prefix=LOCATOR_MAP_PREFIX)
        logger.info("Deleting locator map from db", uuid=locator)

    def delete_watcher_appointment(self, uuid):
        self.delete_entry(uuid, prefix=WATCHER_PREFIX)
        logger.info("Deleting appointment from Watcher's db", uuid=uuid)

    def delete_responder_job(self, uuid):
        self.delete_entry(uuid, prefix=RESPONDER_PREFIX)
        logger.info("Deleting appointment from Responder's db", uuid=uuid)

    def load_last_block_hash_watcher(self):
        return self.get_last_known_block(WATCHER_LAST_BLOCK_KEY)

    def load_last_block_hash_responder(self):
        return self.get_last_known_block(RESPONDER_LAST_BLOCK_KEY)

    def store_last_block_hash_watcher(self, block_hash):
        self.create_entry(WATCHER_LAST_BLOCK_KEY, block_hash)

    def store_last_block_hash_responder(self, block_hash):
        self.create_entry(RESPONDER_LAST_BLOCK_KEY, block_hash)
