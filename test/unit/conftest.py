import pytest
from time import sleep
from threading import Thread

from pisa.api import start_api
from test.simulator.bitcoind_sim import run_simulator


@pytest.fixture(scope='session')
def run_bitcoind():
    bitcoind_thread = Thread(target=run_simulator)
    bitcoind_thread.daemon = True
    bitcoind_thread.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)


@pytest.fixture(scope='session')
def run_api():
    api_thread = Thread(target=start_api)
    api_thread.daemon = True
    api_thread.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)
