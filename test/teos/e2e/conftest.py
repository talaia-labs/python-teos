import os
import shutil
import pytest
import multiprocessing
from grpc import RpcError
from multiprocessing import Process

from teos.teosd import main
from teos.cli.teos_cli import RPCClient
from common.cryptographer import Cryptographer
from test.teos.conftest import config

multiprocessing.set_start_method("spawn")


# This fixture needs to be manually run on the first E2E.
@pytest.fixture(scope="module")
def teosd(run_bitcoind):
    teosd_process, teos_id = run_teosd()

    yield teosd_process, teos_id

    stop_teosd(teosd_process)
    shutil.rmtree(".teos")


def run_teosd():
    sk_file_path = os.path.join(config.get("DATA_DIR"), "teos_sk.der")
    if not os.path.exists(sk_file_path):
        # Generating teos sk so we can return the teos_id
        teos_sk = Cryptographer.generate_key()
        Cryptographer.save_key_file(teos_sk.to_der(), "teos_sk", config.get("DATA_DIR"))
    else:
        teos_sk = Cryptographer.load_private_key_der(Cryptographer.load_key_file(sk_file_path))

    teos_id = Cryptographer.get_compressed_pk(teos_sk.public_key)
    teosd_ready = multiprocessing.Event()

    # Change the default WSGI for Windows
    if os.name == "nt":
        config["WSGI"] = "waitress"
    teosd_process = Process(target=main, kwargs={"config": config, "teosd_ready": teosd_ready})
    teosd_process.start()
    teosd_ready.wait()

    return teosd_process, teos_id


def stop_teosd(teosd_process):
    # FIXME: This is not ideal, but for some reason stop raises socket being closed on the first try here.
    #        Looks like this happens if the teosd process is restarted.
    stopped = False
    while not stopped:
        try:
            rpc_client = RPCClient(config.get("RPC_BIND"), config.get("RPC_PORT"))
            rpc_client.stop()
            stopped = True
        except RpcError:
            print("failed")
            pass

    teosd_process.join()


def build_appointment_data(commitment_tx_id, penalty_tx):
    appointment_data = {"tx": penalty_tx, "tx_id": commitment_tx_id, "to_self_delay": 20}

    return appointment_data
