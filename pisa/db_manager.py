import json
import plyvel

from pisa.logger import Logger
from pisa.conf import WATCHER_PREFIX, RESPONDER_PREFIX, WATCHER_LAST_BLOCK_KEY, RESPONDER_LAST_BLOCK_KEY

logger = Logger("DBManager")


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
        return self.load_appointments_db(prefix=WATCHER_PREFIX)

    def load_responder_jobs(self):
        return self.load_appointments_db(prefix=RESPONDER_PREFIX)

    def store_watcher_appointment(self, uuid, appointment):
        self.create_entry(uuid, appointment, prefix=WATCHER_PREFIX)
        logger.info("Adding appointment to Watchers's db", uuid=uuid)

    def store_responder_job(self, uuid, job):
        self.create_entry(uuid, job, prefix=RESPONDER_PREFIX)
        logger.info("Adding appointment to Responder's db", uuid=uuid)

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
