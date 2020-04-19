import pytest
from uuid import uuid4
from shutil import rmtree
from threading import Thread
from coincurve import PrivateKey

from teos.carrier import Carrier
from teos.tools import bitcoin_cli
from teos.responder import Responder
from teos.gatekeeper import UserInfo
from teos.chain_monitor import ChainMonitor
from teos.appointments_dbm import AppointmentsDBM
from teos.block_processor import BlockProcessor
from teos.watcher import Watcher, AppointmentLimitReached
from teos.gatekeeper import Gatekeeper, AuthenticationFailure, NotEnoughSlots

from common.tools import compute_locator
from common.cryptographer import Cryptographer

from test.teos.unit.conftest import (
    generate_blocks_w_delay,
    generate_dummy_appointment,
    get_random_value_hex,
    generate_keypair,
    get_config,
    bitcoind_feed_params,
    bitcoind_connect_params,
)

APPOINTMENTS = 5
TEST_SET_SIZE = 200

config = get_config()

signing_key, public_key = generate_keypair()

# Reduce the maximum number of appointments to something we can test faster
MAX_APPOINTMENTS = 100


@pytest.fixture(scope="session")
def temp_db_manager():
    db_name = get_random_value_hex(8)
    db_manager = AppointmentsDBM(db_name)

    yield db_manager

    db_manager.db.close()
    rmtree(db_name)


@pytest.fixture(scope="module")
def watcher(db_manager, gatekeeper):
    block_processor = BlockProcessor(bitcoind_connect_params)
    carrier = Carrier(bitcoind_connect_params)

    responder = Responder(db_manager, gatekeeper, carrier, block_processor)
    watcher = Watcher(db_manager, gatekeeper, block_processor, responder, signing_key.to_der(), MAX_APPOINTMENTS)

    chain_monitor = ChainMonitor(
        watcher.block_queue, watcher.responder.block_queue, block_processor, bitcoind_feed_params
    )
    chain_monitor.monitor_chain()

    return watcher


@pytest.fixture(scope="module")
def txids():
    return [get_random_value_hex(32) for _ in range(100)]


@pytest.fixture(scope="module")
def locator_uuid_map(txids):
    return {compute_locator(txid): uuid4().hex for txid in txids}


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


def test_init(run_bitcoind, watcher):
    assert isinstance(watcher.appointments, dict) and len(watcher.appointments) == 0
    assert isinstance(watcher.locator_uuid_map, dict) and len(watcher.locator_uuid_map) == 0
    assert watcher.block_queue.empty()
    assert isinstance(watcher.db_manager, AppointmentsDBM)
    assert isinstance(watcher.gatekeeper, Gatekeeper)
    assert isinstance(watcher.block_processor, BlockProcessor)
    assert isinstance(watcher.responder, Responder)
    assert isinstance(watcher.max_appointments, int)
    assert isinstance(watcher.signing_key, PrivateKey)


def test_add_appointment_non_registered(watcher):
    # Appointments from non-registered users should fail
    user_sk, user_pk = generate_keypair()

    appointment, dispute_tx = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    with pytest.raises(AuthenticationFailure, match="User not found"):
        watcher.add_appointment(appointment, appointment_signature)


def test_add_appointment_no_slots(watcher):
    # Appointments from register users with no available slots should aso fail
    user_sk, user_pk = generate_keypair()
    user_id = Cryptographer.get_compressed_pk(user_pk)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=0, subscription_expiry=10)

    appointment, dispute_tx = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    with pytest.raises(NotEnoughSlots):
        watcher.add_appointment(appointment, appointment_signature)


def test_add_appointment(watcher):
    # Simulate the user is registered
    user_sk, user_pk = generate_keypair()
    available_slots = 100
    user_id = Cryptographer.get_compressed_pk(user_pk)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=available_slots, subscription_expiry=10)

    appointment, dispute_tx = generate_dummy_appointment()
    appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

    response = watcher.add_appointment(appointment, appointment_signature)
    assert response.get("locator") == appointment.locator
    assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
        Cryptographer.recover_pk(appointment.serialize(), response.get("signature"))
    )
    assert response.get("available_slots") == available_slots - 1

    # Check that we can also add an already added appointment (same locator)
    response = watcher.add_appointment(appointment, appointment_signature)
    assert response.get("locator") == appointment.locator
    assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
        Cryptographer.recover_pk(appointment.serialize(), response.get("signature"))
    )
    # The slot count should not have been reduced and only one copy is kept.
    assert response.get("available_slots") == available_slots - 1
    assert len(watcher.locator_uuid_map[appointment.locator]) == 1

    # If two appointments with the same locator come from different users, they are kept.
    another_user_sk, another_user_pk = generate_keypair()
    another_user_id = Cryptographer.get_compressed_pk(another_user_pk)
    watcher.gatekeeper.registered_users[another_user_id] = UserInfo(
        available_slots=available_slots, subscription_expiry=10
    )

    appointment_signature = Cryptographer.sign(appointment.serialize(), another_user_sk)
    response = watcher.add_appointment(appointment, appointment_signature)
    assert response.get("locator") == appointment.locator
    assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
        Cryptographer.recover_pk(appointment.serialize(), response.get("signature"))
    )
    assert response.get("available_slots") == available_slots - 1
    assert len(watcher.locator_uuid_map[appointment.locator]) == 2


def test_add_too_many_appointments(watcher):
    # Simulate the user is registered
    user_sk, user_pk = generate_keypair()
    available_slots = 100
    user_id = Cryptographer.get_compressed_pk(user_pk)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(available_slots=available_slots, subscription_expiry=10)

    # Appointments on top of the limit should be rejected
    watcher.appointments = dict()

    for i in range(MAX_APPOINTMENTS):
        appointment, dispute_tx = generate_dummy_appointment()
        appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)

        response = watcher.add_appointment(appointment, appointment_signature)
        assert response.get("locator") == appointment.locator
        assert Cryptographer.get_compressed_pk(watcher.signing_key.public_key) == Cryptographer.get_compressed_pk(
            Cryptographer.recover_pk(appointment.serialize(), response.get("signature"))
        )
        assert response.get("available_slots") == available_slots - (i + 1)

    with pytest.raises(AppointmentLimitReached):
        appointment, dispute_tx = generate_dummy_appointment()
        appointment_signature = Cryptographer.sign(appointment.serialize(), user_sk)
        watcher.add_appointment(appointment, appointment_signature)


def test_do_watch(watcher, temp_db_manager):
    watcher.db_manager = temp_db_manager

    # We will wipe all the previous data and add 5 appointments
    appointments, locator_uuid_map, dispute_txs = create_appointments(APPOINTMENTS)

    # Set the data into the Watcher and in the db
    watcher.locator_uuid_map = locator_uuid_map
    watcher.appointments = {}
    watcher.gatekeeper.registered_users = {}

    # Simulate a register (times out in 10 bocks)
    user_id = get_random_value_hex(16)
    watcher.gatekeeper.registered_users[user_id] = UserInfo(
        available_slots=100, subscription_expiry=watcher.block_processor.get_block_count() + 10
    )

    # Add the appointments
    for uuid, appointment in appointments.items():
        watcher.appointments[uuid] = {"locator": appointment.locator, "user_id": user_id, "size": 200}
        watcher.gatekeeper.registered_users[user_id].appointments.append(uuid)
        watcher.db_manager.store_watcher_appointment(uuid, appointment.to_dict())
        watcher.db_manager.create_append_locator_map(appointment.locator, uuid)

    do_watch_thread = Thread(target=watcher.do_watch, daemon=True)
    do_watch_thread.start()

    # Broadcast the first two
    for dispute_tx in dispute_txs[:2]:
        bitcoin_cli(bitcoind_connect_params).sendrawtransaction(dispute_tx)

    # After generating a block, the appointment count should have been reduced by 2 (two breaches)
    generate_blocks_w_delay(1)

    assert len(watcher.appointments) == APPOINTMENTS - 2

    # The rest of appointments will timeout after the subscription times-out (9 more blocks) + EXPIRY_DELTA
    # Wait for an additional block to be safe
    generate_blocks_w_delay(10 + config.get("EXPIRY_DELTA"))

    assert len(watcher.appointments) == 0

    # FIXME: We should also add cases where the transactions are invalid. bitcoind_mock needs to be extended for this.


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


def test_filter_breaches_random_data(watcher):
    appointments = {}
    locator_uuid_map = {}
    breaches = {}

    for i in range(TEST_SET_SIZE):
        dummy_appointment, _ = generate_dummy_appointment()
        uuid = uuid4().hex
        appointments[uuid] = {"locator": dummy_appointment.locator, "user_id": dummy_appointment.user_id}
        watcher.db_manager.store_watcher_appointment(uuid, dummy_appointment.to_dict())
        watcher.db_manager.create_append_locator_map(dummy_appointment.locator, uuid)

        locator_uuid_map[dummy_appointment.locator] = [uuid]

        if i % 2:
            dispute_txid = get_random_value_hex(32)
            breaches[dummy_appointment.locator] = dispute_txid

    watcher.locator_uuid_map = locator_uuid_map
    watcher.appointments = appointments

    valid_breaches, invalid_breaches = watcher.filter_breaches(breaches)

    # We have "triggered" TEST_SET_SIZE/2 breaches, all of them invalid.
    assert len(valid_breaches) == 0 and len(invalid_breaches) == TEST_SET_SIZE / 2


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
    dummy_appointment.encrypted_blob = encrypted_blob
    dummy_appointment.locator = compute_locator(dispute_txid)
    uuid = uuid4().hex

    appointments = {uuid: dummy_appointment}
    locator_uuid_map = {dummy_appointment.locator: [uuid]}
    breaches = {dummy_appointment.locator: dispute_txid}

    for uuid, appointment in appointments.items():
        watcher.appointments[uuid] = {"locator": appointment.locator, "user_id": appointment.user_id}
        watcher.db_manager.store_watcher_appointment(uuid, dummy_appointment.to_dict())
        watcher.db_manager.create_append_locator_map(dummy_appointment.locator, uuid)

    watcher.locator_uuid_map = locator_uuid_map

    valid_breaches, invalid_breaches = watcher.filter_breaches(breaches)

    # We have "triggered" a single breach and it was valid.
    assert len(invalid_breaches) == 0 and len(valid_breaches) == 1
