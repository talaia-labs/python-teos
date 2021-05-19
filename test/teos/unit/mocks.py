from threading import Event

from test.teos.conftest import get_random_value_hex
from teos.appointments_dbm import WATCHER_PREFIX, WATCHER_LAST_BLOCK_KEY


class BlockProcessor:
    """ A simple BlockProcessor mock"""

    def __init__(self, *args, **kwargs):
        self.bitcoind_reachable = Event()
        self.bitcoind_reachable.set()

    @staticmethod
    def get_block_count(*args, **kwargs):
        return 0

    @staticmethod
    def get_block(*args, **kwargs):
        return {"height": 0, "tx": []}

    @staticmethod
    def get_best_block_hash(*args, **kwargs):
        return get_random_value_hex(32)

    @staticmethod
    def decode_raw_transaction(*args, **kwargs):
        return {}

    def get_distance_to_tip(self, *args, **kwargs):
        pass


class Carrier:
    """ A simple Carrier mock"""

    def __init__(self, *args, **kwargs):
        pass

    def send_transaction(self, *args, **kwargs):
        pass

    def get_transaction(self, *args, **kwargs):
        pass


class Gatekeeper:
    """ A simple Gatekeeper mock"""

    def __init__(self, user_db, block_processor, *args, **kwargs):
        self.registered_users = dict()
        self.outdated_users_cache = {}
        self.user_db = user_db
        self.block_processor = block_processor

    @property
    def n_registered_users(self):
        return len(self.registered_users)

    def add_update_user(self, *args, **kwargs):
        pass

    def authenticate_user(self, *args, **kwargs):
        pass

    def has_subscription_expired(self, *args, **kwargs):
        pass

    def add_update_appointment(self, *args, **kwargs):
        pass

    def get_user_info(self, *args, **kwargs):
        pass

    def get_outdated_appointments(self, *args, **kwargs):
        pass

    def delete_appointments(self, *args, **kwargs):
        pass


class Responder:
    """ A simple Responder mock"""

    def __init__(self, *args, **kwargs):
        self.trackers = {}

    def has_tracker(self, *args, **kwargs):
        pass

    def get_tracker(self, *args, **kwargs):
        pass

    def handle_breach(self, *args, **kwargs):
        pass


class AppointmentsDBM:
    """ A mock that stores all the data related to appointments in memory instead of using a database"""

    def __init__(self):
        self.appointments = dict()
        self.trackers = dict()
        self.triggered_appointments = set()
        self.last_known_block_watcher = None
        self.last_known_block_responder = None
        self.data = dict()

    def load_appointments_db(self, prefix):
        if prefix == WATCHER_PREFIX:
            return self.appointments
        else:
            return self.trackers

    def get_last_known_block(self, key):
        if key == WATCHER_LAST_BLOCK_KEY:
            return self.last_known_block_watcher
        else:
            return self.last_known_block_responder

    def load_watcher_appointment(self, uuid):
        return self.appointments.get(uuid)

    def load_responder_tracker(self, uuid):
        return self.trackers.get(uuid)

    def load_watcher_appointments(self, include_triggered=False):
        appointments = self.appointments
        if not include_triggered:
            not_triggered = list(set(appointments.keys()).difference(self.triggered_appointments))
            appointments = {uuid: appointments[uuid] for uuid in not_triggered}
        return appointments

    def load_responder_trackers(self):
        return self.trackers

    def store_watcher_appointment(self, uuid, appointment):
        self.appointments[uuid] = appointment

    def store_responder_tracker(self, uuid, tracker):
        self.trackers[uuid] = tracker

    def delete_watcher_appointment(self, uuid):
        del self.appointments[uuid]

    def batch_delete_watcher_appointments(self, uuids):
        for uuid in uuids:
            self.delete_watcher_appointment(uuid)

    def delete_responder_tracker(self, uuid):
        del self.trackers[uuid]

    def batch_delete_responder_trackers(self, uuids):
        for uuid in uuids:
            self.delete_responder_tracker(uuid)

    def load_last_block_hash_watcher(self):
        return self.last_known_block_watcher

    def load_last_block_hash_responder(self):
        return self.last_known_block_responder

    def store_last_block_hash_watcher(self, block_hash):
        self.last_known_block_watcher = block_hash

    def store_last_block_hash_responder(self, block_hash):
        self.last_known_block_responder = block_hash

    def create_triggered_appointment_flag(self, uuid):
        self.triggered_appointments.add(uuid)

    def batch_create_triggered_appointment_flag(self, uuids):
        self.triggered_appointments.update(uuids)

    def load_all_triggered_flags(self):
        return list(self.triggered_appointments)

    def delete_triggered_appointment_flag(self, uuid):
        self.triggered_appointments.remove(uuid)

    def batch_delete_triggered_appointment_flag(self, uuids):
        for uuid in uuids:
            self.delete_triggered_appointment_flag(uuid)


class UsersDBM:
    """ A mock that stores all the data related to users in memory instead of using a database"""

    def __init__(self):
        self.users = dict()

    def store_user(self, user_id, user_data):
        self.users[user_id] = user_data

    def load_user(self, user_id):
        return self.users[user_id]

    def delete_user(self, user_id):
        del self.users[user_id]

    def load_all_users(self):
        return self.users
