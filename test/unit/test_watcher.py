import pytest
import logging
from os import urandom
from time import sleep
from uuid import uuid4
from hashlib import sha256
from threading import Thread
from queue import Queue, Empty

from pisa.watcher import Watcher
from pisa.responder import Responder
from pisa.conf import MAX_APPOINTMENTS
from pisa.appointment import Appointment
from pisa.tools import check_txid_format
from pisa.utils.auth_proxy import AuthServiceProxy
from test.simulator.bitcoind_sim import TIME_BETWEEN_BLOCKS
from pisa.conf import EXPIRY_DELTA, BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT

logging.getLogger().disabled = True
APPOINTMENTS = 5
START_TIME_OFFSET = 1
END_TIME_OFFSET = 1


@pytest.fixture(scope="module")
def watcher():
    return Watcher()


def create_appointment(locator=None):
    bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT))

    if locator is None:
        locator = urandom(32).hex()

    start_time = bitcoin_cli.getblockcount() + 1
    end_time = start_time + 1
    dispute_delta = 20
    encrypted_blob_data = urandom(100).hex()
    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    return Appointment(locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function)


def create_appointments(n):
    locator_uuid_map = dict()
    appointments = dict()
    txids = []

    for i in range(n):
        txid = urandom(32)
        uuid = uuid4().hex
        locator = sha256(txid).hexdigest()

        appointments[uuid] = create_appointment(locator)
        locator_uuid_map[locator] = [uuid]
        txids.append(txid.hex())

    return appointments, locator_uuid_map, txids


def test_init(watcher):
    assert type(watcher.appointments) is dict and len(watcher.appointments) == 0
    assert type(watcher.locator_uuid_map) is dict and len(watcher.locator_uuid_map) == 0
    assert watcher.block_queue is None
    assert watcher.asleep is True
    assert watcher.max_appointments == MAX_APPOINTMENTS
    assert watcher.zmq_subscriber is None
    assert type(watcher.responder) is Responder


def test_add_appointment(run_bitcoind, watcher):
    # The watcher automatically fire do_watch and do_subscribe on adding an appointment if it is asleep (initial state).
    # Avoid this by setting the state to awake.
    watcher.asleep = False

    # We should be able to add appointments up to the limit
    for _ in range(10):
        added_appointment = watcher.add_appointment(create_appointment())

        assert added_appointment is True


def test_add_too_many_appointments(watcher):
    # Any appointment on top of those should fail
    watcher.appointments = dict()

    for _ in range(MAX_APPOINTMENTS):
        added_appointment = watcher.add_appointment(create_appointment())

        assert added_appointment is True

    added_appointment = watcher.add_appointment(create_appointment())

    assert added_appointment is False


def test_do_subscribe(watcher):
    watcher.block_queue = Queue()

    zmq_thread = Thread(target=watcher.do_subscribe)
    zmq_thread.daemon = True
    zmq_thread.start()

    try:
        block_hash = watcher.block_queue.get(timeout=MAX_APPOINTMENTS)
        assert check_txid_format(block_hash)

    except Empty:
        assert False


def test_do_watch(watcher):
    bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT))

    # We will wipe all the previous data and add 5 appointments
    watcher.appointments, watcher.locator_uuid_map, txids = create_appointments(APPOINTMENTS)

    watch_thread = Thread(target=watcher.do_watch)
    watch_thread.daemon = True
    watch_thread.start()

    # Broadcast the first two
    for txid in txids[:2]:
        bitcoin_cli.sendrawtransaction(txid)

    # After leaving some time for the block to be mined and processed, the number of appointments should have reduced
    # by two
    sleep(TIME_BETWEEN_BLOCKS*(START_TIME_OFFSET+END_TIME_OFFSET + 1))
    assert len(watcher.appointments) == APPOINTMENTS - 2

    # The rest of appointments will timeout after the end (2) + EXPIRY_DELTA
    # Wait for an additional block to be safe

    sleep((EXPIRY_DELTA + 2 + 1) * TIME_BETWEEN_BLOCKS)

    assert len(watcher.appointments) == 0
    assert watcher.asleep is True
