import os
import pytest
import random
import subprocess
from time import sleep
from os import makedirs
from shutil import rmtree, copy
from decimal import Decimal, getcontext

from teos.teosd import get_config

import bitcoin
import bitcoin.rpc
from bitcoin.core import b2lx, b2x, x

bitcoin.SelectParams("regtest")

getcontext().prec = 10
utxos = list()
btc_addr = None


cmd_args = {"BTC_NETWORK": "regtest"}
config = get_config(cmd_args, ".teos")

bitcoin_cli = bitcoin.rpc.Proxy(
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


@pytest.fixture(scope="session")
def run_bitcoind(dirname=".test_bitcoin"):
    try:
        # Run bitcoind in a separate folder
        makedirs(dirname, exist_ok=True)

        bitcoind = os.getenv("BITCOIND", "bitcoind")

        copy(os.path.join(os.path.dirname(__file__), "bitcoin.conf"), dirname)
        subprocess.Popen([bitcoind, f"--datadir={dirname}"])

        # Generate some initial blocks
        setup_node()
        yield

    finally:
        bitcoin_cli.call("stop")
        rmtree(dirname)


def setup_node():
    global btc_addr

    # Check bitcoind is running while generating the address
    while True:
        # FIXME: Not creating a new bitcoin_cli here creates one of those Request-Sent errors I don't know how to fix
        #        Not a big deal, but it would be nicer not having to.
        bitcoin_cli = bitcoin.rpc.Proxy(
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

        except (ConnectionError, bitcoin.rpc.InWarmupError):
            sleep(1)

    print("Address:", btc_addr)

    # Mine enough blocks so coinbases are mature and we have enough funds to run everything
    bitcoin_cli.generatetoaddress(105, btc_addr)
    create_initial_transactions()


def create_initial_transactions(fee=Decimal("0.00005")):
    utxos = bitcoin_cli.listunspent()
    btc_addresses = [str(bitcoin_cli.getnewaddress()) for _ in range(100)]
    for utxo in utxos:
        # Create 100 outputs per utxo and mine a new block.
        outpoint = utxo.get("outpoint")
        tx_ins = {"txid": b2lx(outpoint.hash), "vout": outpoint.n}

        amount = Decimal(utxo.get("amount") / 100_000_000)
        tx_outs = {btc_address: str(amount / 100) for btc_address in btc_addresses[:-1]}
        tx_outs[btc_addresses[-1]] = str((amount / 100) - fee)

        raw_tx_hex = bitcoin_cli.call("createrawtransaction", [tx_ins], tx_outs)
        tx = bitcoin.rpc.CTransaction.deserialize(bytes.fromhex(raw_tx_hex))
        signed_tx = bitcoin_cli.signrawtransactionwithwallet(tx)
        bitcoin_cli.sendrawtransaction(signed_tx.get("tx"))

        bitcoin_cli.generatetoaddress(1, btc_addr)


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
    while utxo.get("amount") < Decimal("0.00002"):
        utxo = utxos.pop(0)

    return utxo


def generate_blocks(n):
    return list(map(b2lx, bitcoin_cli.generatetoaddress(n, btc_addr)))


def generate_blocks_with_delay(n, delay=0.2):
    block_ids = []
    for _ in range(n):
        block_ids.extend(generate_blocks(1))
        sleep(delay)

    return block_ids


def makeCTransaction(rawtx):
    return bitcoin.core.CTransaction.deserialize(x(rawtx))


def generate_block_with_transactions(commitment_txs):
    # If a list of transactions is passed, send them all
    if isinstance(commitment_txs, list):
        for tx in commitment_txs:
            bitcoin_cli.sendrawtransaction(makeCTransaction(tx))
    elif isinstance(commitment_txs, str):
        bitcoin_cli.sendrawtransaction(makeCTransaction(commitment_txs))
    else:
        raise TypeError(f"Expected a string or a list of strings, not a {type(commitment_txs).__name__}.")

    return generate_blocks(1)


def create_commitment_tx(utxo=None, destination=None, fee=Decimal("0.00001")):
    if not utxo:
        utxo = get_utxo()

    # We will set the recipient to ourselves if destination is None
    if destination is None:
        destination = utxo.get("address")

    outpoint = utxo.get("outpoint")
    amount = Decimal(utxo.get("amount") / 100_000_000)
    commitment_tx_ins = {"txid": b2lx(outpoint.hash), "vout": outpoint.n}
    commitment_tx_outs = {str(destination): str(amount - fee)}

    raw_commitment_tx = bitcoin_cli.call("createrawtransaction", [commitment_tx_ins], commitment_tx_outs)
    tx = bitcoin.rpc.CTransaction.deserialize(bytes.fromhex(raw_commitment_tx))
    signed_commitment_tx = bitcoin_cli.signrawtransactionwithwallet(tx)

    if not signed_commitment_tx.get("complete"):
        raise ValueError("Couldn't sign transaction. {}".format(signed_commitment_tx))

    return signed_commitment_tx.get("tx")


def create_penalty_tx(decoded_commitment_tx, destination=None, fee=Decimal("0.00001")):
    # We will set the recipient to ourselves if destination is None
    if destination is None:
        destination = decoded_commitment_tx.get("vout")[0].get("scriptPubKey").get("addresses")[0]

    penalty_tx_ins = {"txid": decoded_commitment_tx.get("txid"), "vout": 0}
    penalty_tx_outs = {str(destination): str(decoded_commitment_tx.get("vout")[0].get("value") - fee)}

    orphan_info = {
        "txid": decoded_commitment_tx.get("txid"),
        "scriptPubKey": decoded_commitment_tx.get("vout")[0].get("scriptPubKey").get("hex"),
        "vout": 0,
        "amount": str(decoded_commitment_tx.get("vout")[0].get("value")),
    }

    raw_penalty_tx = bitcoin_cli.call("createrawtransaction", [penalty_tx_ins], penalty_tx_outs)
    tx = bitcoin.rpc.CTransaction.deserialize(bytes.fromhex(raw_penalty_tx))
    signed_penalty_tx = bitcoin_cli.signrawtransactionwithwallet(tx, [orphan_info])

    if not signed_penalty_tx.get("complete"):
        raise ValueError("Couldn't sign orphan transaction. {}".format(signed_penalty_tx))

    return signed_penalty_tx.get("tx")


def create_txs():
    signed_commitment_tx = create_commitment_tx()
    decoded_commitment_tx = bitcoin_cli.call("decoderawtransaction", b2x(signed_commitment_tx.serialize()))

    signed_penalty_tx = create_penalty_tx(decoded_commitment_tx)

    return signed_commitment_tx, decoded_commitment_tx.get("txid"), signed_penalty_tx
