import pytest
import random
import requests
from time import sleep
from threading import Thread

from pisa.conf import DB_PATH
from pisa.api import start_api
from pisa.watcher import Watcher
from pisa.db_manager import DBManager
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


@pytest.fixture(scope='session')
def db_manager():
    return DBManager('test_db')


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


