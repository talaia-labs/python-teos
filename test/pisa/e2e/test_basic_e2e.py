import json
from time import sleep
from decimal import Decimal, getcontext

import pisa.conf as conf
from pisa import HOST, PORT
from pisa.utils.auth_proxy import AuthServiceProxy

from common.tools import compute_locator

from apps.cli import pisa_cli


getcontext().prec = 10

bitcoin_cli = AuthServiceProxy(
    "http://%s:%s@%s:%d" % (conf.BTC_RPC_USER, conf.BTC_RPC_PASSWD, conf.BTC_RPC_HOST, 18444)
)

END_TIME_DELTA = 10


def create_txs():
    utxos = bitcoin_cli.listunspent()

    if len(utxos) == 0:
        raise ValueError("There's no UTXOs.")

    commitment_tx_ins = {"txid": utxos[0].get("txid"), "vout": utxos[0].get("vout")}
    commitment_tx_outs = {utxos[0].get("address"): utxos[0].get("amount") - Decimal(1 / pow(10, 5))}

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


def build_appointment_data(commitment_tx, penalty_tx):
    commitment_tx_id = bitcoin_cli.decoderawtransaction(commitment_tx).get("txid")
    current_height = bitcoin_cli.getblockcount()

    appointment_data = {
        "tx": penalty_tx,
        "tx_id": commitment_tx_id,
        "start_time": current_height + 1,
        "end_time": current_height + 1 + END_TIME_DELTA,
        "to_self_delay": 20,
    }

    return appointment_data


def test_appointment_life_cycle():
    commitment_tx, penalty_tx = create_txs()
    appointment_data = build_appointment_data(commitment_tx, penalty_tx)

    # We'll use pisa_cli to add the appointment. The expected input format is a list of arguments with a json-encoded
    # appointment
    pisa_cli.pisa_api_server = HOST
    pisa_cli.pisa_api_port = PORT

    response = pisa_cli.add_appointment([json.dumps(appointment_data)])
    assert response is True

    # Broadcast the commitment transaction and mine a block
    new_addr = bitcoin_cli.getnewaddress()
    bitcoin_cli.sendrawtransaction(commitment_tx)
    bitcoin_cli.generatetoaddress(1, new_addr)

    # Check that the justice has been triggered (the appointment has moved from Watcher to Responder)
    locator = compute_locator(appointment_data.get("tx_id"))

    # Let's add a bit of delay so the state can be updated
    sleep(1)
    appointment_info = pisa_cli.get_appointment([locator])

    assert appointment_info is not None
    assert len(appointment_info) == 1
    assert appointment_info[0].get("status") == "dispute_responded"

    # Now let's mine some blocks so the appointment reaches its end.
    # Since we are running all the nodes remotely data may take more time than normal, and some confirmations may be
    # missed, so we generate more than enough confirmations and add some delays.
    for _ in range(int(1.5 * END_TIME_DELTA)):
        sleep(1)
        bitcoin_cli.generatetoaddress(1, new_addr)

    appointment_info = pisa_cli.get_appointment([locator])
    assert appointment_info[0].get("status") == "not_found"
