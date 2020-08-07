import time
import pytest
from uuid import uuid4
from binascii import hexlify
from threading import Thread

import teos.rpc as rpc
from teos.watcher import Watcher
from teos.responder import Responder
import teos.cli.teos_cli as teos_cli
from teos.internal_api import InternalAPI
from teos.teosd import INTERNAL_API_ENDPOINT

from test.teos.conftest import config
from test.teos.unit.conftest import generate_keypair


MAX_APPOINTMENTS = 100
user_sk, user_pk = generate_keypair()
user_id = hexlify(user_pk.format(compressed=True)).decode("utf-8")

teos_sk, teos_pk = generate_keypair()
teos_id = hexlify(teos_pk.format(compressed=True)).decode("utf-8")


@pytest.fixture(scope="module", autouse=True)
def rpc_server():
    Thread(
        target=rpc.serve, args=[config.get("RPC_BIND"), config.get("RPC_PORT"), INTERNAL_API_ENDPOINT], daemon=True
    ).start()
    time.sleep(1)


@pytest.fixture(scope="module", autouse=True)
def internal_api(db_manager, gatekeeper, carrier, block_processor):
    responder = Responder(db_manager, gatekeeper, carrier, block_processor)
    watcher = Watcher(
        db_manager, gatekeeper, block_processor, responder, teos_sk, MAX_APPOINTMENTS, config.get("LOCATOR_CACHE_SIZE")
    )
    watcher.last_known_block = block_processor.get_best_block_hash()
    i_api = InternalAPI(watcher, INTERNAL_API_ENDPOINT)
    i_api.rpc_server.start()

    yield i_api

    i_api.rpc_server.stop(None)


def test_get_all_appointments_empty():
    appointments = teos_cli.get_all_appointments(config.get("RPC_BIND"), config.get("RPC_PORT"))
    assert len(appointments.get("watcher_appointments")) == 0 and len(appointments.get("responder_trackers")) == 0


# FIXME: 194 will do with dummy appointment
def test_get_all_appointments_watcher(internal_api, generate_dummy_appointment):
    # Data is pulled straight from the database, so we need to feed some
    appointment, _ = generate_dummy_appointment()
    uuid = uuid4().hex
    internal_api.watcher.db_manager.store_watcher_appointment(uuid, appointment.to_dict())
    appointments = teos_cli.get_all_appointments(config.get("RPC_BIND"), config.get("RPC_PORT"))
    assert len(appointments.get("watcher_appointments")) == 1 and len(appointments.get("responder_trackers")) == 0
    assert appointments.get("watcher_appointments")[uuid] == appointment.to_dict()

    # Delete the data
    internal_api.watcher.db_manager.delete_watcher_appointment(uuid)


# FIXME: 194 will do with dummy tracker
def test_get_all_appointments_responder(internal_api, generate_dummy_tracker):
    # Data is pulled straight from the database, so we need to feed some
    tracker = generate_dummy_tracker()
    uuid = uuid4().hex
    internal_api.watcher.db_manager.store_responder_tracker(uuid, tracker.to_dict())
    appointments = teos_cli.get_all_appointments(config.get("RPC_BIND"), config.get("RPC_PORT"))
    assert len(appointments.get("watcher_appointments")) == 0 and len(appointments.get("responder_trackers")) == 1
    assert appointments.get("responder_trackers")[uuid] == tracker.to_dict()

    # Delete the data
    internal_api.watcher.db_manager.delete_responder_tracker(uuid)


# FIXME: 194 will do with dummy appointments and trackers
def test_get_all_appointments_both(internal_api, generate_dummy_appointment, generate_dummy_tracker):
    # Data is pulled straight from the database, so we need to feed some
    appointment, _ = generate_dummy_appointment()
    uuid_appointment = uuid4().hex
    internal_api.watcher.db_manager.store_watcher_appointment(uuid_appointment, appointment.to_dict())

    tracker = generate_dummy_tracker()
    uuid_tracker = uuid4().hex
    internal_api.watcher.db_manager.store_responder_tracker(uuid_tracker, tracker.to_dict())

    appointments = teos_cli.get_all_appointments(config.get("RPC_BIND"), config.get("RPC_PORT"))
    assert len(appointments.get("watcher_appointments")) == 1 and len(appointments.get("responder_trackers")) == 1
    assert appointments.get("watcher_appointments")[uuid_appointment] == appointment.to_dict()
    assert appointments.get("responder_trackers")[uuid_tracker] == tracker.to_dict()
