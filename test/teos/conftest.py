import os
import pytest
import random
import subprocess
from time import sleep
from os import makedirs
from shutil import rmtree, copy
from decimal import Decimal, getcontext

from teos.teosd import get_config
from teos.utils.auth_proxy import AuthServiceProxy, JSONRPCException


getcontext().prec = 10
utxos = list()
btc_addr = None


cmd_args = {"BTC_NETWORK": "regtest"}
config = get_config(cmd_args, ".teos")

bitcoin_cli = AuthServiceProxy(
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
def run_bitcoind(dirname=".test_bitcoin"):
    # Run bitcoind in a separate folder
    makedirs(dirname, exist_ok=True)

    bitcoind = os.getenv("BITCOIND", "bitcoind")

    copy(os.path.join(os.path.dirname(__file__), "bitcoin.conf"), dirname)
    subprocess.Popen([bitcoind, f"--datadir={dirname}"])

    # Generate some initial blocks
    setup_node()
    yield

    bitcoin_cli.stop()
    rmtree(dirname)


def setup_node():
    global btc_addr

    # Check bitcoind is running while generating the address
    while True:
        # FIXME: Not creating a new bitcoin_cli here creates one of those Request-Sent errors I don't know how to fix
        #        Not a big deal, but it would be nicer not having to.
        bitcoin_cli = AuthServiceProxy(
            "http://%s:%s@%s:%d"
            % (
                config.get("BTC_RPC_USER"),
                config.get("BTC_RPC_PASSWORD"),
                config.get("BTC_RPC_CONNECT"),
                config.get("BTC_RPC_PORT"),
            )
        )
        try:
            btc_addr = bitcoin_cli.getnewaddress()
            break

        except ConnectionError:
            sleep(1)
        except JSONRPCException as e:
            if "Loading wallet..." in str(e):
                sleep(1)

    # Mine enough blocks so coinbases are mature and we have enough funds to run everything
    bitcoin_cli.generatetoaddress(200, btc_addr)


def get_random_value_hex(nbytes):
    pseudo_random_value = random.getrandbits(8 * nbytes)
    prv_hex = "{:x}".format(pseudo_random_value)
    return prv_hex.zfill(2 * nbytes)


def get_utxo():
    global utxos
    if not utxos:
        utxos = bitcoin_cli.listunspent()

    if len(utxos) == 0:
        raise ValueError("There are no UTXOs.")

    utxo = utxos.pop(0)
    while utxo.get("amount") < Decimal(2 / pow(10, 5)):
        utxo = utxos.pop(0)

    return utxo


def generate_blocks(n):
    return bitcoin_cli.generatetoaddress(n, btc_addr)


def generate_blocks_w_delay(n):
    block_ids = []
    for _ in range(n):
        block_ids.append(generate_blocks(1))
        sleep(0.2)

    return block_ids


def generate_block_with_transactions(commitment_txs):
    # If a list of transactions is passed, send them all
    if isinstance(commitment_txs, list):
        for tx in commitment_txs:
            bitcoin_cli.sendrawtransaction(tx)
    elif isinstance(commitment_txs, str):
        bitcoin_cli.sendrawtransaction(commitment_txs)

    return generate_blocks(1)


def create_commitment_tx(utxo=None, destination=None, fee=Decimal(1 / pow(10, 5))):
    if not utxo:
        utxo = get_utxo()

    # We will set the recipient to ourselves if destination is None
    if destination is None:
        destination = utxo.get("address")

    commitment_tx_ins = {"txid": utxo.get("txid"), "vout": utxo.get("vout")}
    commitment_tx_outs = {destination: utxo.get("amount") - fee}

    raw_commitment_tx = bitcoin_cli.createrawtransaction([commitment_tx_ins], commitment_tx_outs)
    signed_commitment_tx = bitcoin_cli.signrawtransactionwithwallet(raw_commitment_tx)

    if not signed_commitment_tx.get("complete"):
        raise ValueError("Couldn't sign transaction. {}".format(signed_commitment_tx))

    return signed_commitment_tx.get("hex")


def create_penalty_tx(decoded_commitment_tx, destination=None, fee=Decimal(1 / pow(10, 5))):
    # We will set the recipient to ourselves if destination is None
    if destination is None:
        destination = decoded_commitment_tx.get("vout")[0].get("scriptPubKey").get("addresses")[0]

    penalty_tx_ins = {"txid": decoded_commitment_tx.get("txid"), "vout": 0}
    penalty_tx_outs = {destination: decoded_commitment_tx.get("vout")[0].get("value") - fee}

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


def create_txs():
    signed_commitment_tx = create_commitment_tx()
    decoded_commitment_tx = bitcoin_cli.decoderawtransaction(signed_commitment_tx)

    signed_penalty_tx = create_penalty_tx(decoded_commitment_tx)

    return signed_commitment_tx, decoded_commitment_tx.get("txid"), signed_penalty_tx
