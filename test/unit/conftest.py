import pytest
import random
import requests
from time import sleep
from shutil import rmtree
from threading import Thread

from pisa.conf import DB_PATH
from pisa.api import start_api
from pisa.responder import Job
from pisa.watcher import Watcher
from pisa.db_manager import DBManager
from pisa.appointment import Appointment
from test.simulator.bitcoind_sim import run_simulator, HOST, PORT


@pytest.fixture(scope='session')
def run_bitcoind():
    bitcoind_thread = Thread(target=run_simulator, kwargs={"mode": "event"})
    bitcoind_thread.daemon = True
    bitcoind_thread.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)


@pytest.fixture(scope='session')
def run_api():
    db_manager = DBManager(DB_PATH)
    watcher = Watcher(db_manager)

    api_thread = Thread(target=start_api, args=[watcher])
    api_thread.daemon = True
    api_thread.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)


@pytest.fixture(scope='session', autouse=True)
def prng_seed():
    random.seed(0)


@pytest.fixture(scope='module')
def db_manager():
    manager = DBManager('test_db')
    yield manager

    manager.db.close()
    rmtree('test_db')


def get_random_value_hex(nbytes):
    pseudo_random_value = random.getrandbits(8*nbytes)
    prv_hex = '{:x}'.format(pseudo_random_value)
    return prv_hex.zfill(2*nbytes)


def generate_block():
    requests.post(url="http://{}:{}/generate".format(HOST, PORT), timeout=5)
    sleep(0.5)


def generate_blocks(n):
    for _ in range(n):
        generate_block()


def generate_dummy_appointment():
    locator = get_random_value_hex(32)
    encrypted_blob = get_random_value_hex(250)
    start_time = 100
    end_time = 120
    dispute_delta = 20
    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    appointment_data = dict(locator=locator, start_time=start_time, end_time=end_time, dispute_delta=dispute_delta,
                            encrypted_blob=encrypted_blob, cipher=cipher, hash_function=hash_function, triggered=False)

    return Appointment.from_dict(appointment_data)


def generate_dummy_job():
    dispute_txid = get_random_value_hex(32)
    justice_txid = get_random_value_hex(32)
    justice_rawtx = get_random_value_hex(100)

    job_data = dict(dispute_txid=dispute_txid, justice_txid=justice_txid, justice_rawtx=justice_rawtx,
                    appointment_end=100)

    return Job.from_dict(job_data)

