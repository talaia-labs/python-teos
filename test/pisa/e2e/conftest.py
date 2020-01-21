import pytest
import random
from decimal import Decimal, getcontext

import pisa.conf as conf
from pisa.utils.auth_proxy import AuthServiceProxy

getcontext().prec = 10
END_TIME_DELTA = 10


@pytest.fixture()
def bitcoin_cli():
    # return AuthServiceProxy("http://%s:%s@%s:%d" % (conf.BTC_RPC_USER, conf.BTC_RPC_PASSWD, conf.BTC_RPC_HOST, 18444))
    return AuthServiceProxy(
        "http://%s:%s@%s:%d" % (conf.BTC_RPC_USER, conf.BTC_RPC_PASSWD, conf.BTC_RPC_HOST, conf.BTC_RPC_PORT)
    )


@pytest.fixture(scope="session", autouse=True)
def prng_seed():
    random.seed(0)


def get_random_value_hex(nbytes):
    pseudo_random_value = random.getrandbits(8 * nbytes)
    prv_hex = "{:x}".format(pseudo_random_value)
    return prv_hex.zfill(2 * nbytes)


@pytest.fixture()
def create_txs(bitcoin_cli):
    set_up_node(bitcoin_cli)
    utxos = bitcoin_cli.listunspent()

    if len(utxos) == 0:
        raise ValueError("There're no UTXOs.")

    utxo = utxos.pop(0)
    while utxo.get("amount") < Decimal(2 / pow(10, 5)):
        utxo = utxos.pop(0)

    commitment_tx_ins = {"txid": utxo.get("txid"), "vout": utxo.get("vout")}
    commitment_tx_outs = {utxo.get("address"): utxo.get("amount") - Decimal(1 / pow(10, 5))}

    raw_commitment_tx = bitcoin_cli.createrawtransaction([commitment_tx_ins], commitment_tx_outs)
    signed_commitment_tx = bitcoin_cli.signrawtransactionwithwallet(raw_commitment_tx)

    if not signed_commitment_tx.get("complete"):
        raise ValueError("Couldn't sign transaction. {}".format(signed_commitment_tx))

    decoded_commitment_tx = bitcoin_cli.decoderawtransaction(signed_commitment_tx.get("hex"))

    penalty_tx_ins = {"txid": decoded_commitment_tx.get("txid"), "vout": 0}
    address = decoded_commitment_tx.get("vout")[0].get("scriptPubKey").get("addresses")[0]
    penalty_tx_outs = {address: decoded_commitment_tx.get("vout")[0].get("value") - Decimal(1 / pow(10, 5))}

    orphan_info = {
        "txid": decoded_commitment_tx.get("txid"),
        "scriptPubKey": decoded_commitment_tx.get("vout")[0].get("scriptPubKey").get("hex"),
        "vout": 0,
        "amount": decoded_commitment_tx.get("vout")[0].get("value"),
    }

    raw_penalty_tx = bitcoin_cli.createrawtransaction([penalty_tx_ins], penalty_tx_outs)
    signed_penalty_tx = bitcoin_cli.signrawtransactionwithwallet(raw_penalty_tx, [orphan_info])

    if not signed_penalty_tx.get("complete"):
        raise ValueError("Couldn't sign orphan transaction. {}".format(signed_commitment_tx))

    return signed_commitment_tx.get("hex"), signed_penalty_tx.get("hex")


def set_up_node(bitcoin_cli):
    # This method will create a new address a mine bitcoin so the node can be used for testing
    new_addr = bitcoin_cli.getnewaddress()
    bitcoin_cli.generatetoaddress(101, new_addr)


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
