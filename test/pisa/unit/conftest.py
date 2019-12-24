import pytest
import random
import requests
from time import sleep
from shutil import rmtree
from threading import Thread
from binascii import hexlify

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from apps.cli.blob import Blob
from pisa.responder import TransactionTracker
from pisa.watcher import Watcher
from pisa.tools import bitcoin_cli
from pisa.db_manager import DBManager
from common.appointment import Appointment

from bitcoind_mock.utils import sha256d
from bitcoind_mock.transaction import TX
from bitcoind_mock.bitcoind import BitcoindMock
from bitcoind_mock.conf import BTC_RPC_HOST, BTC_RPC_PORT

from common.constants import LOCATOR_LEN_HEX
from common.cryptographer import Cryptographer


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


@pytest.fixture(scope="session")
def db_manager():
    manager = DBManager("test_db")
    yield manager

    manager.db.close()
    rmtree("test_db")


def generate_keypair():
    client_sk = ec.generate_private_key(ec.SECP256K1, default_backend())
    client_pk = client_sk.public_key()

    return client_sk, client_pk


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


def generate_dummy_appointment_data(real_height=True, start_time_offset=5, end_time_offset=30):
    if real_height:
        current_height = bitcoin_cli().getblockcount()

    else:
        current_height = 10

    dispute_tx = TX.create_dummy_transaction()
    dispute_txid = sha256d(dispute_tx)
    penalty_tx = TX.create_dummy_transaction(dispute_txid)

    dummy_appointment_data = {
        "tx": penalty_tx,
        "tx_id": dispute_txid,
        "start_time": current_height + start_time_offset,
        "end_time": current_height + end_time_offset,
        "to_self_delay": 20,
    }

    # dummy keys for this test
    client_sk, client_pk = generate_keypair()
    client_pk_der = client_pk.public_bytes(
        encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    locator = Watcher.compute_locator(dispute_txid)
    blob = Blob(dummy_appointment_data.get("tx"))

    encrypted_blob = Cryptographer.encrypt(blob, dummy_appointment_data.get("tx_id"))

    appointment_data = {
        "locator": locator,
        "start_time": dummy_appointment_data.get("start_time"),
        "end_time": dummy_appointment_data.get("end_time"),
        "to_self_delay": dummy_appointment_data.get("to_self_delay"),
        "encrypted_blob": encrypted_blob,
    }

    signature = Cryptographer.sign(Appointment.from_dict(appointment_data).serialize(), client_sk)
    pk_hex = hexlify(client_pk_der).decode("utf-8")

    data = {"appointment": appointment_data, "signature": signature, "public_key": pk_hex}

    return data, dispute_tx


def generate_dummy_appointment(real_height=True, start_time_offset=5, end_time_offset=30):
    appointment_data, dispute_tx = generate_dummy_appointment_data(
        real_height=real_height, start_time_offset=start_time_offset, end_time_offset=end_time_offset
    )

    return Appointment.from_dict(appointment_data["appointment"]), dispute_tx


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
    config = {
        "BTC_RPC_USER": "username",
        "BTC_RPC_PASSWD": "password",
        "BTC_RPC_HOST": "localhost",
        "BTC_RPC_PORT": 8332,
        "BTC_NETWORK": "regtest",
        "FEED_PROTOCOL": "tcp",
        "FEED_ADDR": "127.0.0.1",
        "FEED_PORT": 28332,
        "MAX_APPOINTMENTS": 100,
        "EXPIRY_DELTA": 6,
        "MIN_TO_SELF_DELAY": 20,
        "SERVER_LOG_FILE": "pisa.log",
        "PISA_SECRET_KEY": "pisa_sk.der",
        "CLIENT_LOG_FILE": "pisa.log",
        "TEST_LOG_FILE": "test.log",
        "DB_PATH": "appointments",
    }

    return config
