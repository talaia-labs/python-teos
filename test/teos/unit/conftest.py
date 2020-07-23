import pytest
from shutil import rmtree
from coincurve import PrivateKey

from teos import DEFAULT_CONF
from teos.carrier import Carrier
from teos.users_dbm import UsersDBM
from teos.gatekeeper import Gatekeeper
from teos.responder import TransactionTracker
from teos.block_processor import BlockProcessor
from teos.appointments_dbm import AppointmentsDBM
from teos.extended_appointment import ExtendedAppointment

from common.tools import compute_locator
from common.constants import LOCATOR_LEN_HEX
from common.cryptographer import Cryptographer

from test.teos.conftest import get_config as general_get_config
from test.teos.conftest import bitcoin_cli, get_random_value_hex, create_txs, create_commitment_tx, create_penalty_tx

# Set params to connect to regtest for testing
DEFAULT_CONF["BTC_RPC_PORT"]["value"] = 18443
DEFAULT_CONF["BTC_NETWORK"]["value"] = "regtest"

bitcoind_connect_params = {k: v["value"] for k, v in DEFAULT_CONF.items() if k.startswith("BTC")}


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
def gatekeeper(user_db_manager, block_processor):
    return Gatekeeper(
        user_db_manager,
        block_processor,
        get_config().get("SUBSCRIPTION_SLOTS"),
        get_config().get("SUBSCRIPTION_DURATION"),
        get_config().get("EXPIRY_DELTA"),
    )


def generate_keypair():
    sk = PrivateKey()
    pk = sk.public_key

    return sk, pk


def fork(block_hash):
    # fork_endpoint = "http://{}:{}/fork".format(BTC_RPC_HOST, BTC_RPC_PORT)
    # requests.post(fork_endpoint, json={"parent": block_hash})
    pass


def generate_dummy_appointment():
    commitment_tx, commitment_txid, penalty_tx = create_txs()

    dummy_appointment_data = {"tx": penalty_tx, "tx_id": commitment_txid, "to_self_delay": 20}

    appointment_data = {
        "locator": compute_locator(commitment_txid),
        "to_self_delay": dummy_appointment_data.get("to_self_delay"),
        "encrypted_blob": Cryptographer.encrypt(penalty_tx, commitment_txid),
        "user_id": get_random_value_hex(16),
        "user_signature": get_random_value_hex(50),
        "start_block": 200,
    }

    return ExtendedAppointment.from_dict(appointment_data), commitment_tx


def generate_dummy_tracker(commitment_tx=None):
    if not commitment_tx:
        commitment_tx = create_commitment_tx()
    decoded_commitment_tx = bitcoin_cli.decoderawtransaction(commitment_tx)
    penalty_tx = create_penalty_tx(decoded_commitment_tx)
    locator = decoded_commitment_tx.get("txid")[:LOCATOR_LEN_HEX]

    tracker_data = dict(
        locator=locator,
        dispute_txid=bitcoin_cli.decoderawtransaction(commitment_tx).get("txid"),
        penalty_txid=bitcoin_cli.decoderawtransaction(penalty_tx).get("txid"),
        penalty_rawtx=penalty_tx,
        user_id="02" + get_random_value_hex(32),
    )

    return TransactionTracker.from_dict(tracker_data)


def get_config():
    return general_get_config(".", "teos.conf", DEFAULT_CONF)
