import pytest
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

from pisa import c_logger
from pisa.watcher import Watcher
from pisa.responder import Responder
from pisa.tools import check_txid_format, bitcoin_cli
from test.unit.conftest import generate_block, generate_blocks, generate_dummy_appointment, get_random_value_hex
from pisa.conf import EXPIRY_DELTA, PISA_SECRET_KEY, MAX_APPOINTMENTS

c_logger.disabled = True

APPOINTMENTS = 5
START_TIME_OFFSET = 1
END_TIME_OFFSET = 1
TEST_SET_SIZE = 200

with open(PISA_SECRET_KEY, "r") as key_file:
    pubkey_pem = key_file.read().encode("utf-8")
    # TODO: should use the public key file instead, but it is not currently exported in the configuration
    signing_key = load_pem_private_key(pubkey_pem, password=None, backend=default_backend())
    public_key = signing_key.public_key()


@pytest.fixture(scope="module")
def watcher(db_manager):
    return Watcher(db_manager)


@pytest.fixture(scope="module")
def txids():
    return [get_random_value_hex(32) for _ in range(100)]


@pytest.fixture(scope="module")
def locator_uuid_map(txids):
    return {sha256(unhexlify(txid)).hexdigest(): uuid4().hex for txid in txids}


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


def test_init_no_key(db_manager):
    try:
        Watcher(db_manager, pisa_sk_file=None)
        assert False

    except ValueError:
        assert True


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

        # Check that we can also add an already added appointment (same locator)
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
    # We will wipe all the previous data and add 5 appointments
    watcher.appointments, watcher.locator_uuid_map, dispute_txs = create_appointments(APPOINTMENTS)

    watch_thread = Thread(target=watcher.do_watch)
    watch_thread.daemon = True
    watch_thread.start()

    # Broadcast the first two
    for dispute_tx in dispute_txs[:2]:
        bitcoin_cli().sendrawtransaction(dispute_tx)

    # After leaving some time for the block to be mined and processed, the number of appointments should have reduced
    # by two
    generate_blocks(START_TIME_OFFSET + END_TIME_OFFSET)

    assert len(watcher.appointments) == APPOINTMENTS - 2

    # The rest of appointments will timeout after the end (2) + EXPIRY_DELTA
    # Wait for an additional block to be safe
    generate_blocks(EXPIRY_DELTA + START_TIME_OFFSET + END_TIME_OFFSET)

    assert len(watcher.appointments) == 0
    assert watcher.asleep is True


def test_matches(watcher, txids, locator_uuid_map):
    watcher.locator_uuid_map = locator_uuid_map
    potential_matches = watcher.get_matches(txids)

    # All the txids must match
    assert locator_uuid_map.keys() == potential_matches.keys()


def test_matches_random_data(watcher, locator_uuid_map):
    # The likelihood of finding a potential match with random data should be negligible
    watcher.locator_uuid_map = locator_uuid_map
    txids = [get_random_value_hex(32) for _ in range(TEST_SET_SIZE)]

    potential_matches = watcher.get_matches(txids)

    # None of the txids should match
    assert len(potential_matches) == 0


def test_filter_valid_matches_random_data(watcher):
    appointments = {}
    locator_uuid_map = {}
    matches = {}

    for i in range(TEST_SET_SIZE):
        dummy_appointment, _ = generate_dummy_appointment()
        uuid = uuid4().hex
        appointments[uuid] = dummy_appointment

        locator_uuid_map[dummy_appointment.locator] = [uuid]

        if i % 2:
            dispute_txid = get_random_value_hex(32)
            matches[dummy_appointment.locator] = dispute_txid

    watcher.locator_uuid_map = locator_uuid_map
    watcher.appointments = appointments

    filtered_valid_matches = watcher.filter_valid_matches(matches)

    assert not any([fil_match["valid_match"] for uuid, fil_match in filtered_valid_matches.items()])


def test_filter_valid_matches(watcher):
    dispute_txid = "0437cd7f8525ceed2324359c2d0ba26006d92d856a9c20fa0241106ee5a597c9"
    encrypted_blob = (
        "29f55518945408f567bb7feb4d7bb15ba88b7d8ca0223a44d5c67dfe32d038caee7613e35736025d95ad4ecd6538a50"
        "74cbe8d7739705697a5dc4d19b8a6e4459ed2d1b0d0a9b18c49bc2187dcbfb4046b14d58a1add83235fc632efc398d5"
        "0abcb7738f1a04b3783d025c1828b4e8a8dc8f13f2843e6bc3bf08eade02fc7e2c4dce7d2f83b055652e944ac114e0b"
        "72a9abcd98fd1d785a5d976c05ed780e033e125fa083c6591b6029aa68dbc099f148a2bc2e0cb63733e68af717d48d5"
        "a312b5f5b2fcca9561b2ff4191f9cdff936a43f6efef4ee45fbaf1f18d0a4b006f3fc8399dd8ecb21f709d4583bba14"
        "4af6d49fa99d7be2ca21059a997475aa8642b66b921dc7fc0321b6a2f6927f6f9bab55c75e17a19dc3b2ae895b6d4a4"
        "f64f8eb21b1e"
    )

    dummy_appointment, _ = generate_dummy_appointment()
    dummy_appointment.encrypted_blob.data = encrypted_blob
    dummy_appointment.locator = sha256(unhexlify(dispute_txid)).hexdigest()
    uuid = uuid4().hex

    appointments = {uuid: dummy_appointment}
    locator_uuid_map = {dummy_appointment.locator: [uuid]}
    matches = {dummy_appointment.locator: dispute_txid}

    watcher.appointments = appointments
    watcher.locator_uuid_map = locator_uuid_map

    filtered_valid_matches = watcher.filter_valid_matches(matches)

    assert all([fil_match["valid_match"] for uuid, fil_match in filtered_valid_matches.items()])
