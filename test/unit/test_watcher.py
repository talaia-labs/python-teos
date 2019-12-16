import pytest
from uuid import uuid4
from threading import Thread
from queue import Queue, Empty
from cryptography.hazmat.primitives import serialization

from pisa import c_logger
from pisa.watcher import Watcher
from pisa.responder import Responder
from pisa.tools import bitcoin_cli
from test.unit.conftest import (
    generate_block,
    generate_blocks,
    generate_dummy_appointment,
    get_random_value_hex,
    generate_keypair,
)
from pisa.conf import EXPIRY_DELTA, MAX_APPOINTMENTS

from common.tools import check_sha256_hex_format
from common.cryptographer import Cryptographer

c_logger.disabled = True

APPOINTMENTS = 5
START_TIME_OFFSET = 1
END_TIME_OFFSET = 1
TEST_SET_SIZE = 200


signing_key, public_key = generate_keypair()
sk_der = signing_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption(),
)


@pytest.fixture(scope="module")
def watcher(db_manager):
    return Watcher(db_manager, sk_der)


@pytest.fixture(scope="module")
def txids():
    return [get_random_value_hex(32) for _ in range(100)]


@pytest.fixture(scope="module")
def locator_uuid_map(txids):
    return {Watcher.compute_locator(txid): uuid4().hex for txid in txids}


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
        assert Cryptographer.verify(Cryptographer.signature_format(appointment.to_dict()), sig, public_key)

        # Check that we can also add an already added appointment (same locator)
        added_appointment, sig = watcher.add_appointment(appointment)

        assert added_appointment is True
        assert Cryptographer.verify(Cryptographer.signature_format(appointment.to_dict()), sig, public_key)


def test_add_too_many_appointments(watcher):
    # Any appointment on top of those should fail
    watcher.appointments = dict()

    for _ in range(MAX_APPOINTMENTS):
        appointment, dispute_tx = generate_dummy_appointment(
            start_time_offset=START_TIME_OFFSET, end_time_offset=END_TIME_OFFSET
        )
        added_appointment, sig = watcher.add_appointment(appointment)

        assert added_appointment is True
        assert Cryptographer.verify(Cryptographer.signature_format(appointment.to_dict()), sig, public_key)

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
        assert check_sha256_hex_format(block_hash)

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


def test_get_breaches(watcher, txids, locator_uuid_map):
    watcher.locator_uuid_map = locator_uuid_map
    potential_breaches = watcher.get_breaches(txids)

    # All the txids must breach
    assert locator_uuid_map.keys() == potential_breaches.keys()


def test_get_breaches_random_data(watcher, locator_uuid_map):
    # The likelihood of finding a potential breach with random data should be negligible
    watcher.locator_uuid_map = locator_uuid_map
    txids = [get_random_value_hex(32) for _ in range(TEST_SET_SIZE)]

    potential_breaches = watcher.get_breaches(txids)

    # None of the txids should breach
    assert len(potential_breaches) == 0


def test_filter_valid_breaches_random_data(watcher):
    appointments = {}
    locator_uuid_map = {}
    breaches = {}

    for i in range(TEST_SET_SIZE):
        dummy_appointment, _ = generate_dummy_appointment()
        uuid = uuid4().hex
        appointments[uuid] = dummy_appointment

        locator_uuid_map[dummy_appointment.locator] = [uuid]

        if i % 2:
            dispute_txid = get_random_value_hex(32)
            breaches[dummy_appointment.locator] = dispute_txid

    watcher.locator_uuid_map = locator_uuid_map
    watcher.appointments = appointments

    filtered_valid_breaches = watcher.filter_valid_breaches(breaches)

    assert not any([fil_breach["valid_breach"] for uuid, fil_breach in filtered_valid_breaches.items()])


def test_filter_valid_breaches(watcher):
    dispute_txid = "0437cd7f8525ceed2324359c2d0ba26006d92d856a9c20fa0241106ee5a597c9"
    encrypted_blob = (
        "a62aa9bb3c8591e4d5de10f1bd49db92432ce2341af55762cdc9242c08662f97f5f47da0a1aa88373508cd6e67e87eefddeca0cee98c1"
        "967ec1c1ecbb4c5e8bf08aa26159214e6c0bc4b2c7c247f87e7601d15c746fc4e711be95ba0e363001280138ba9a65b06c4aa6f592b21"
        "3635ee763984d522a4c225814510c8f7ab0801f36d4a68f5ee7dd3930710005074121a172c29beba79ed647ebaf7e7fab1bbd9a208251"
        "ef5486feadf2c46e33a7d66adf9dbbc5f67b55a34b1b3c4909dd34a482d759b0bc25ecd2400f656db509466d7479b5b92a2fadabccc9e"
        "c8918da8979a9feadea27531643210368fee494d3aaa4983e05d6cf082a49105e2f8a7c7821899239ba7dee12940acd7d8a629894b5d31"
        "e94b439cfe8d2e9f21e974ae5342a70c91e8"
    )

    dummy_appointment, _ = generate_dummy_appointment()
    dummy_appointment.encrypted_blob.data = encrypted_blob
    dummy_appointment.locator = Watcher.compute_locator(dispute_txid)
    uuid = uuid4().hex

    appointments = {uuid: dummy_appointment}
    locator_uuid_map = {dummy_appointment.locator: [uuid]}
    breaches = {dummy_appointment.locator: dispute_txid}

    watcher.appointments = appointments
    watcher.locator_uuid_map = locator_uuid_map

    filtered_valid_breaches = watcher.filter_valid_breaches(breaches)

    assert all([fil_breach["valid_breach"] for uuid, fil_breach in filtered_valid_breaches.items()])
