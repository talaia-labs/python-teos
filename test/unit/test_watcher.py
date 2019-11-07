import pytest
from uuid import uuid4
from threading import Thread
from queue import Queue, Empty

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature

from pisa import c_logger
from pisa.watcher import Watcher
from pisa.responder import Responder
from pisa.tools import check_txid_format
from pisa.utils.auth_proxy import AuthServiceProxy
from test.unit.conftest import generate_block, generate_blocks, generate_dummy_appointment
from pisa.conf import (
    EXPIRY_DELTA,
    BTC_RPC_USER,
    BTC_RPC_PASSWD,
    BTC_RPC_HOST,
    BTC_RPC_PORT,
    PISA_SECRET_KEY,
    MAX_APPOINTMENTS,
)

c_logger.disabled = True

APPOINTMENTS = 5
START_TIME_OFFSET = 1
END_TIME_OFFSET = 1

with open(PISA_SECRET_KEY, "r") as key_file:
    pubkey_pem = key_file.read().encode("utf-8")
    # TODO: should use the public key file instead, but it is not currently exported in the configuration
    signing_key = load_pem_private_key(pubkey_pem, password=None, backend=default_backend())
    public_key = signing_key.public_key()


@pytest.fixture(scope="module")
def watcher(db_manager):
    return Watcher(db_manager)


def create_appointments(n):
    locator_uuid_map = dict()
    appointments = dict()
    dispute_txs = []

    for i in range(n):
        appointment, dispute_tx = generate_dummy_appointment(
            start_time_offset=START_TIME_OFFSET, end_time_offset=END_TIME_OFFSET
        )
        uuid = uuid4().hex

        appointments[uuid] = appointment
        locator_uuid_map[appointment.locator] = [uuid]
        dispute_txs.append(dispute_tx)

    return appointments, locator_uuid_map, dispute_txs


def is_signature_valid(appointment, signature, pk):
    # verify the signature
    try:
        data = appointment.serialize()
        pk.verify(signature, data, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False
    return True


def test_init(watcher):
    assert type(watcher.appointments) is dict and len(watcher.appointments) == 0
    assert type(watcher.locator_uuid_map) is dict and len(watcher.locator_uuid_map) == 0
    assert watcher.block_queue.empty()
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
        appointment, dispute_tx = generate_dummy_appointment(
            start_time_offset=START_TIME_OFFSET, end_time_offset=END_TIME_OFFSET
        )
        added_appointment, sig = watcher.add_appointment(appointment)

        assert added_appointment is True
        assert is_signature_valid(appointment, sig, public_key)


def test_sign_appointment(watcher):
    appointment, _ = generate_dummy_appointment(start_time_offset=START_TIME_OFFSET, end_time_offset=END_TIME_OFFSET)
    signature = watcher.sign_appointment(appointment)
    assert is_signature_valid(appointment, signature, public_key)


def test_add_too_many_appointments(watcher):
    # Any appointment on top of those should fail
    watcher.appointments = dict()

    for _ in range(MAX_APPOINTMENTS):
        appointment, dispute_tx = generate_dummy_appointment(
            start_time_offset=START_TIME_OFFSET, end_time_offset=END_TIME_OFFSET
        )
        added_appointment, sig = watcher.add_appointment(appointment)

        assert added_appointment is True
        assert is_signature_valid(appointment, sig, public_key)

    appointment, dispute_tx = generate_dummy_appointment(
        start_time_offset=START_TIME_OFFSET, end_time_offset=END_TIME_OFFSET
    )
    added_appointment, sig = watcher.add_appointment(appointment)

    assert added_appointment is False
    assert sig is None


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
        bitcoin_cli.sendrawtransaction(dispute_tx)

    # After leaving some time for the block to be mined and processed, the number of appointments should have reduced
    # by two
    generate_blocks(START_TIME_OFFSET + END_TIME_OFFSET)

    assert len(watcher.appointments) == APPOINTMENTS - 2

    # The rest of appointments will timeout after the end (2) + EXPIRY_DELTA
    # Wait for an additional block to be safe
    generate_blocks(EXPIRY_DELTA + START_TIME_OFFSET + END_TIME_OFFSET)

    assert len(watcher.appointments) == 0
    assert watcher.asleep is True
