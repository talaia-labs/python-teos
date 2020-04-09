import pytest
import random
import requests
from time import sleep
from shutil import rmtree
from threading import Thread
from coincurve import PrivateKey

from bitcoind_mock.bitcoind import BitcoindMock
from bitcoind_mock.conf import BTC_RPC_HOST, BTC_RPC_PORT
from bitcoind_mock.transaction import create_dummy_transaction

from teos import DEFAULT_CONF
from teos.carrier import Carrier
from teos.tools import bitcoin_cli
from teos.users_dbm import UsersDBM
from teos.gatekeeper import Gatekeeper
from teos.responder import TransactionTracker
from teos.block_processor import BlockProcessor
from teos.appointments_dbm import AppointmentsDBM

from common.tools import compute_locator
from common.appointment import Appointment
from common.constants import LOCATOR_LEN_HEX
from common.config_loader import ConfigLoader
from common.cryptographer import Cryptographer

# Set params to connect to regtest for testing
DEFAULT_CONF["BTC_RPC_PORT"]["value"] = 18443
DEFAULT_CONF["BTC_NETWORK"]["value"] = "regtest"

bitcoind_connect_params = {k: v["value"] for k, v in DEFAULT_CONF.items() if k.startswith("BTC")}
bitcoind_feed_params = {k: v["value"] for k, v in DEFAULT_CONF.items() if k.startswith("FEED")}


@pytest.fixture(scope="session")
def run_bitcoind():
    bitcoind_thread = Thread(target=BitcoindMock().run, kwargs={"mode": "event", "verbose": True})
    bitcoind_thread.daemon = True
    bitcoind_thread.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)


@pytest.fixture(scope="session", autouse=True)
def prng_seed():
    random.seed(0)


@pytest.fixture(scope="module")
def db_manager():
    manager = AppointmentsDBM("test_db")
    # Add last know block for the Responder in the db

    yield manager

    manager.db.close()
    rmtree("test_db")


@pytest.fixture(scope="module")
def user_db_manager():
    manager = UsersDBM("test_user_db")
    # Add last know block for the Responder in the db

    yield manager

    manager.db.close()
    rmtree("test_user_db")


@pytest.fixture(scope="module")
def carrier():
    return Carrier(bitcoind_connect_params)


@pytest.fixture(scope="module")
def block_processor():
    return BlockProcessor(bitcoind_connect_params)


@pytest.fixture(scope="module")
def gatekeeper(user_db_manager):
    return Gatekeeper(user_db_manager, get_config().get("DEFAULT_SLOTS"))


def generate_keypair():
    sk = PrivateKey()
    pk = sk.public_key

    return sk, pk


def get_random_value_hex(nbytes):
    pseudo_random_value = random.getrandbits(8 * nbytes)
    prv_hex = "{:x}".format(pseudo_random_value)
    return prv_hex.zfill(2 * nbytes)


def generate_block():
    requests.post(url="http://{}:{}/generate".format(BTC_RPC_HOST, BTC_RPC_PORT), timeout=5)
    sleep(0.5)


def generate_blocks(n):
    for _ in range(n):
        generate_block()


def fork(block_hash):
    fork_endpoint = "http://{}:{}/fork".format(BTC_RPC_HOST, BTC_RPC_PORT)
    requests.post(fork_endpoint, json={"parent": block_hash})


def generate_dummy_appointment(real_height=True, start_time_offset=5, end_time_offset=30):
    if real_height:
        current_height = bitcoin_cli(bitcoind_connect_params).getblockcount()

    else:
        current_height = 10

    dispute_tx = create_dummy_transaction()
    dispute_txid = dispute_tx.tx_id.hex()
    penalty_tx = create_dummy_transaction(dispute_txid)

    dummy_appointment_data = {
        "tx": penalty_tx.hex(),
        "tx_id": dispute_txid,
        "start_time": current_height + start_time_offset,
        "end_time": current_height + end_time_offset,
        "to_self_delay": 20,
    }

    locator = compute_locator(dispute_txid)

    encrypted_blob = Cryptographer.encrypt(dummy_appointment_data.get("tx"), dummy_appointment_data.get("tx_id"))

    appointment_data = {
        "locator": locator,
        "start_time": dummy_appointment_data.get("start_time"),
        "end_time": dummy_appointment_data.get("end_time"),
        "to_self_delay": dummy_appointment_data.get("to_self_delay"),
        "encrypted_blob": encrypted_blob,
    }

    return Appointment.from_dict(appointment_data), dispute_tx.hex()


def generate_dummy_tracker():
    dispute_txid = get_random_value_hex(32)
    penalty_txid = get_random_value_hex(32)
    penalty_rawtx = get_random_value_hex(100)
    locator = dispute_txid[:LOCATOR_LEN_HEX]

    tracker_data = dict(
        locator=locator,
        dispute_txid=dispute_txid,
        penalty_txid=penalty_txid,
        penalty_rawtx=penalty_rawtx,
        appointment_end=100,
    )

    return TransactionTracker.from_dict(tracker_data)


def get_config():
    config_loader = ConfigLoader(".", "teos.conf", DEFAULT_CONF, {})
    config = config_loader.build_config()

    return config
