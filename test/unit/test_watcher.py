import pytest
import logging
from uuid import uuid4
from hashlib import sha256
from threading import Thread
from binascii import unhexlify
from queue import Queue, Empty

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

from apps.cli.blob import Blob
from pisa.watcher import Watcher
from pisa.responder import Responder
from pisa.conf import MAX_APPOINTMENTS
from pisa.appointment import Appointment
from pisa.tools import check_txid_format
from test.simulator.utils import sha256d
from test.simulator.transaction import TX
from test.unit.conftest import generate_block
from pisa.utils.auth_proxy import AuthServiceProxy
from pisa.conf import EXPIRY_DELTA, BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT, SIGNING_KEY_FILE

logging.getLogger().disabled = True

APPOINTMENTS = 5
START_TIME_OFFSET = 1
END_TIME_OFFSET = 1

with open(SIGNING_KEY_FILE, "r") as key_file:
    pubkey_pem = key_file.read().encode("utf-8")
    # TODO: should use the public key file instead, but it is not currently exported in the configuration
    signing_key = load_pem_private_key(pubkey_pem, password=None, backend=default_backend())
    public_key = signing_key.public_key()


@pytest.fixture(scope="module")
def watcher():
    return Watcher()


def generate_dummy_appointment():
    bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT))

    dispute_tx = TX.create_dummy_transaction()
    dispute_txid = sha256d(dispute_tx)
    justice_tx = TX.create_dummy_transaction(dispute_txid)

    start_time = bitcoin_cli.getblockcount() + 1
    end_time = start_time + 1
    dispute_delta = 20

    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    locator = sha256(unhexlify(dispute_txid)).hexdigest()
    blob = Blob(justice_tx, cipher, hash_function)

    encrypted_blob = blob.encrypt(dispute_txid)

    appointment = Appointment(locator, start_time, end_time, dispute_delta, encrypted_blob, cipher, hash_function)

    return appointment, dispute_tx


def create_appointments(n):
    locator_uuid_map = dict()
    appointments = dict()
    dispute_txs = []

    for i in range(n):
        appointment, dispute_tx = generate_dummy_appointment()
        uuid = uuid4().hex

        appointments[uuid] = appointment
        locator_uuid_map[appointment.locator] = [uuid]
        dispute_txs.append(dispute_tx)

    return appointments, locator_uuid_map, dispute_txs


def test_init(watcher):
    assert type(watcher.appointments) is dict and len(watcher.appointments) == 0
    assert type(watcher.locator_uuid_map) is dict and len(watcher.locator_uuid_map) == 0
    assert watcher.block_queue is None
    assert watcher.asleep is True
    assert watcher.max_appointments == MAX_APPOINTMENTS
    assert watcher.zmq_subscriber is None
    assert type(watcher.responder) is Responder


def test_add_appointment(run_bitcoind, watcher):
    # The watcher automatically fires do_watch and do_subscribe on adding an appointment if it is asleep (initial state)
    # Avoid this by setting the state to awake.
    watcher.asleep = False

    # We should be able to add appointments up to the limit
    for _ in range(10):
        appointment, dispute_tx = generate_dummy_appointment()
        added_appointment, sig = watcher.add_appointment(appointment)

        assert added_appointment is True

        # verify the signature
        try:
            data = appointment.to_json().encode('utf-8')
            public_key.verify(sig, data, ec.ECDSA(hashes.SHA256()))
        except InvalidSignature:
            assert False, "The appointment's signature is not correct"


def test_add_too_many_appointments(watcher):
    # Any appointment on top of those should fail
    watcher.appointments = dict()

    for _ in range(MAX_APPOINTMENTS):
        appointment, dispute_tx = generate_dummy_appointment()
        added_appointment, sig = watcher.add_appointment(appointment)

        assert added_appointment is True

    appointment, dispute_tx = generate_dummy_appointment()
    added_appointment, sig = watcher.add_appointment(appointment)

    assert added_appointment is False


def test_do_subscribe(watcher):
    watcher.block_queue = Queue()

    zmq_thread = Thread(target=watcher.do_subscribe)
    zmq_thread.daemon = True
    zmq_thread.start()

    try:
        generate_block()
        block_hash = watcher.block_queue.get()
        assert check_txid_format(block_hash)

    except Empty:
        assert False


def test_do_watch(watcher):
    bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT))

    # We will wipe all the previous data and add 5 appointments
    watcher.appointments, watcher.locator_uuid_map, dispute_txs = create_appointments(APPOINTMENTS)

    watch_thread = Thread(target=watcher.do_watch)
    watch_thread.daemon = True
    watch_thread.start()

    # Broadcast the first two
    for dispute_tx in dispute_txs[:2]:
        r = bitcoin_cli.sendrawtransaction(dispute_tx)

    # After leaving some time for the block to be mined and processed, the number of appointments should have reduced
    # by two
    for _ in range(START_TIME_OFFSET + END_TIME_OFFSET):
        generate_block()

    assert len(watcher.appointments) == APPOINTMENTS - 2

    # The rest of appointments will timeout after the end (2) + EXPIRY_DELTA
    # Wait for an additional block to be safe

    for _ in range(EXPIRY_DELTA + START_TIME_OFFSET + END_TIME_OFFSET):
        generate_block()

    assert len(watcher.appointments) == 0
    assert watcher.asleep is True
