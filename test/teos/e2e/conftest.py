import pytest
import random
from multiprocessing import Process
from decimal import Decimal, getcontext

from teos.teosd import main
from teos import DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF
from teos.utils.auth_proxy import AuthServiceProxy

from common.config_loader import ConfigLoader


getcontext().prec = 10
END_TIME_DELTA = 10


@pytest.fixture(scope="session")
def bitcoin_cli():
    config = get_config(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF)

    return AuthServiceProxy(
        "http://%s:%s@%s:%d"
        % (
            config.get("BTC_RPC_USER"),
            config.get("BTC_RPC_PASSWORD"),
            config.get("BTC_RPC_CONNECT"),
            config.get("BTC_RPC_PORT"),
        )
    )


@pytest.fixture(scope="session", autouse=True)
def prng_seed():
    random.seed(0)


@pytest.fixture(scope="session", autouse=True)
def setup_node(bitcoin_cli):
    # This method will create a new address a mine bitcoin so the node can be used for testing
    new_addr = bitcoin_cli.getnewaddress()
    bitcoin_cli.generatetoaddress(106, new_addr)


@pytest.fixture()
def create_txs(bitcoin_cli):
    utxos = bitcoin_cli.listunspent()

    if len(utxos) == 0:
        raise ValueError("There're no UTXOs.")

    utxo = utxos.pop(0)
    while utxo.get("amount") < Decimal(2 / pow(10, 5)):
        utxo = utxos.pop(0)

    signed_commitment_tx = create_commitment_tx(bitcoin_cli, utxo)
    decoded_commitment_tx = bitcoin_cli.decoderawtransaction(signed_commitment_tx)

    signed_penalty_tx = create_penalty_tx(bitcoin_cli, decoded_commitment_tx)

    return signed_commitment_tx, signed_penalty_tx


@pytest.fixture()
def create_five_txs(bitcoin_cli):
    utxos = bitcoin_cli.listunspent()

    signed_commitment_txs = []
    signed_penalty_txs = []

    for i in range(5):
        if len(utxos) == 0:
            raise ValueError("There're no UTXOs.")

        utxo = utxos.pop(0)
        while utxo.get("amount") < Decimal(2 / pow(10, 5)):
            utxo = utxos.pop(0)

        signed_commitment_tx = create_commitment_tx(bitcoin_cli, utxo)

        signed_commitment_txs.append(signed_commitment_tx)
        decoded_commitment_tx = bitcoin_cli.decoderawtransaction(signed_commitment_tx)

        signed_penalty_txs.append(create_penalty_tx(bitcoin_cli, decoded_commitment_tx))

    return signed_commitment_txs, signed_penalty_txs


def run_teosd():
    teosd_process = Process(target=main, kwargs={"command_line_conf": {}}, daemon=True)
    teosd_process.start()

    return teosd_process


def get_random_value_hex(nbytes):
    pseudo_random_value = random.getrandbits(8 * nbytes)
    prv_hex = "{:x}".format(pseudo_random_value)
    return prv_hex.zfill(2 * nbytes)


def create_commitment_tx(bitcoin_cli, utxo, destination=None):
    # We will set the recipient to ourselves is destination is None
    if destination is None:
        destination = utxo.get("address")

    commitment_tx_ins = {"txid": utxo.get("txid"), "vout": utxo.get("vout")}
    commitment_tx_outs = {destination: utxo.get("amount") - Decimal(1 / pow(10, 5))}

    raw_commitment_tx = bitcoin_cli.createrawtransaction([commitment_tx_ins], commitment_tx_outs)
    signed_commitment_tx = bitcoin_cli.signrawtransactionwithwallet(raw_commitment_tx)

    if not signed_commitment_tx.get("complete"):
        raise ValueError("Couldn't sign transaction. {}".format(signed_commitment_tx))

    return signed_commitment_tx.get("hex")


def create_penalty_tx(bitcoin_cli, decoded_commitment_tx, destination=None):
    # We will set the recipient to ourselves is destination is None
    if destination is None:
        destination = decoded_commitment_tx.get("vout")[0].get("scriptPubKey").get("addresses")[0]

    penalty_tx_ins = {"txid": decoded_commitment_tx.get("txid"), "vout": 0}
    penalty_tx_outs = {destination: decoded_commitment_tx.get("vout")[0].get("value") - Decimal(1 / pow(10, 5))}

    orphan_info = {
        "txid": decoded_commitment_tx.get("txid"),
        "scriptPubKey": decoded_commitment_tx.get("vout")[0].get("scriptPubKey").get("hex"),
        "vout": 0,
        "amount": decoded_commitment_tx.get("vout")[0].get("value"),
    }

    raw_penalty_tx = bitcoin_cli.createrawtransaction([penalty_tx_ins], penalty_tx_outs)
    signed_penalty_tx = bitcoin_cli.signrawtransactionwithwallet(raw_penalty_tx, [orphan_info])

    if not signed_penalty_tx.get("complete"):
        raise ValueError("Couldn't sign orphan transaction. {}".format(signed_penalty_tx))

    return signed_penalty_tx.get("hex")


def build_appointment_data(bitcoin_cli, commitment_tx_id, penalty_tx):
    current_height = bitcoin_cli.getblockcount()

    appointment_data = {
        "tx": penalty_tx,
        "tx_id": commitment_tx_id,
        "start_time": current_height + 1,
        "end_time": current_height + 1 + END_TIME_DELTA,
        "to_self_delay": 20,
    }

    return appointment_data


def get_config(data_folder, conf_file_name, default_conf):
    config_loader = ConfigLoader(data_folder, conf_file_name, default_conf, {})
    config = config_loader.build_config()

    return config
