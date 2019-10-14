import pytest
from time import sleep
from threading import Thread
from multiprocessing import Process

from pisa.api import start_api
from test.simulator.bitcoind_sim import run_simulator

bitcoind_process = Process(target=run_simulator)


@pytest.fixture(scope='session')
def run_bitcoind():
    global bitcoind_process

    bitcoind_process.daemon = True
    bitcoind_process.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)


@pytest.fixture(scope='session')
def run_api():
    api_thread = Thread(target=start_api)
    api_thread.daemon = True
    api_thread.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)
