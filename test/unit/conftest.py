import pytest
import random
import requests
from time import sleep
from shutil import rmtree
from threading import Thread
from hashlib import sha256
from binascii import unhexlify

from apps.cli.blob import Blob
from pisa.responder import Job
from pisa.tools import bitcoin_cli
from pisa.db_manager import DBManager
from pisa.appointment import Appointment
from test.simulator.utils import sha256d
from test.simulator.transaction import TX
from test.simulator.bitcoind_sim import run_simulator, HOST, PORT


@pytest.fixture(scope="session")
def run_bitcoind():
    bitcoind_thread = Thread(target=run_simulator, kwargs={"mode": "event"})
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


def get_random_value_hex(nbytes):
    pseudo_random_value = random.getrandbits(8 * nbytes)
    prv_hex = "{:x}".format(pseudo_random_value)
    return prv_hex.zfill(2 * nbytes)


def generate_block():
    requests.post(url="http://{}:{}/generate".format(HOST, PORT), timeout=5)
    sleep(0.5)


def generate_blocks(n):
    for _ in range(n):
        generate_block()


def generate_dummy_appointment_data(real_height=True, start_time_offset=5, end_time_offset=30):
    if real_height:
        current_height = bitcoin_cli().getblockcount()

    else:
        current_height = 10

    dispute_tx = TX.create_dummy_transaction()
    dispute_txid = sha256d(dispute_tx)
    justice_tx = TX.create_dummy_transaction(dispute_txid)

    dummy_appointment_data = {
        "tx": justice_tx,
        "tx_id": dispute_txid,
        "start_time": current_height + start_time_offset,
        "end_time": current_height + end_time_offset,
        "dispute_delta": 20,
    }

    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    locator = sha256(unhexlify(dispute_txid)).hexdigest()
    blob = Blob(dummy_appointment_data.get("tx"), cipher, hash_function)

    encrypted_blob = blob.encrypt((dummy_appointment_data.get("tx_id")))

    appointment_data = {
        "locator": locator,
        "start_time": dummy_appointment_data.get("start_time"),
        "end_time": dummy_appointment_data.get("end_time"),
        "dispute_delta": dummy_appointment_data.get("dispute_delta"),
        "encrypted_blob": encrypted_blob,
        "cipher": cipher,
        "hash_function": hash_function,
        "triggered": False,
    }

    return appointment_data, dispute_tx


def generate_dummy_appointment(real_height=True, start_time_offset=5, end_time_offset=30):
    appointment_data, dispute_tx = generate_dummy_appointment_data(
        real_height=real_height, start_time_offset=start_time_offset, end_time_offset=end_time_offset
    )

    return Appointment.from_dict(appointment_data), dispute_tx


def generate_dummy_job():
    dispute_txid = get_random_value_hex(32)
    justice_txid = get_random_value_hex(32)
    justice_rawtx = get_random_value_hex(100)

    job_data = dict(
        dispute_txid=dispute_txid, justice_txid=justice_txid, justice_rawtx=justice_rawtx, appointment_end=100
    )

    return Job.from_dict(job_data)
