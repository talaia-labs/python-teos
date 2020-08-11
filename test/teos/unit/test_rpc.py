import time
import pytest
from uuid import uuid4
from binascii import hexlify
from threading import Thread

import teos.rpc as rpc
from teos.watcher import Watcher
from teos.responder import Responder
from teos.cli.teos_cli import RPCClient
from teos.internal_api import InternalAPI
from teos.teosd import INTERNAL_API_ENDPOINT

from test.teos.conftest import config
from test.teos.unit.conftest import generate_keypair


MAX_APPOINTMENTS = 100
user_sk, user_pk = generate_keypair()
user_id = hexlify(user_pk.format(compressed=True)).decode("utf-8")

teos_sk, teos_pk = generate_keypair()
teos_id = hexlify(teos_pk.format(compressed=True)).decode("utf-8")


@pytest.fixture(scope="module", autouse=True)
def rpc_server():
    Thread(
        target=rpc.serve, args=[config.get("RPC_BIND"), config.get("RPC_PORT"), INTERNAL_API_ENDPOINT], daemon=True
    ).start()
    time.sleep(1)


@pytest.fixture(scope="module", autouse=True)
def internal_api(db_manager, gatekeeper, carrier, block_processor):
    responder = Responder(db_manager, gatekeeper, carrier, block_processor)
    watcher = Watcher(
        db_manager, gatekeeper, block_processor, responder, teos_sk, MAX_APPOINTMENTS, config.get("LOCATOR_CACHE_SIZE")
    )
    watcher.last_known_block = block_processor.get_best_block_hash()
    i_api = InternalAPI(watcher, INTERNAL_API_ENDPOINT)
    i_api.rpc_server.start()

    yield i_api

    i_api.rpc_server.stop(None)


@pytest.fixture(scope="module")
def rpc_client():
    return RPCClient(config.get("RPC_BIND"), config.get("RPC_PORT"))


# TODO: add tests for the RPCClient
