from pisa.conf import FEED_PROTOCOL, FEED_ADDR, FEED_PORT
from flask import Flask, request, Response, abort
from test.simulator.zmq_publisher import ZMQPublisher
from threading import Thread
from pisa.rpc_errors import *
from pisa.tools import check_txid_format
import logging
import binascii
import json
import os
import time


app = Flask(__name__)
HOST = 'localhost'
PORT = '18443'

mining_simulator = ZMQPublisher(topic=b'hashblock', feed_protocol=FEED_PROTOCOL, feed_addr=FEED_ADDR,
                                feed_port=FEED_PORT)

mempool = []
mined_transactions = {}
blocks = {}
blockchain = []
TIME_BETWEEN_BLOCKS = 10


@app.route('/', methods=['POST'])
def process_request():
    """
    process_requests simulates the bitcoin-rpc server run by bitcoind. The available commands are limited to the ones
    we'll need to use in pisa. The model we will be using is pretty simplified to reduce the complexity of simulating
    bitcoind:

    Raw transactions:       raw transactions will actually be transaction ids (txids). Pisa will, therefore, receive
                            encrypted blobs that encrypt ids instead of real transactions.

    decoderawtransaction:   querying for the decoding of a raw transaction will return a dictionary with a single
                            field: "txid", which will match with the txid provided in the request

    sendrawtransaction:     sending a rawtransaction will notify our mining simulator to include such transaction in a
                            subsequent block.

    getrawtransaction:      requesting a rawtransaction from a txid will return a dictionary containing a single field:
                            "confirmations", since rawtransactions are only queried to check whether a transaction has
                            made it to a block or not.

    getblockcount:          the block count will be get from the mining simulator by querying how many blocks have been
                            emited so far.

    getblock:               querying for a block will return a dictionary with a three fields: "tx" representing a list
                            of transactions, "height" representing the block height and "hash" representing the block
                            hash. Both will be got from the mining simulator.

    getblockhash:           a block hash is only queried by pisad on bootstrapping to check the network bitcoind is
                            running on.

    help:                   help is only used as a sample command to test if bitcoind is running when bootstrapping
                            pisad. It will return a 200/OK with no data.
    """

    global mempool
    request_data = request.get_json()
    method = request_data.get('method')

    response = {"id": 0, "result": 0, "error": None}
    no_param_err = {"code": RPC_MISC_ERROR, "message": "JSON value is not a {} as expected"}

    if method == "decoderawtransaction":
        txid = get_param(request_data)

        if isinstance(txid, str):
            if check_txid_format(txid):
                response["result"] = {"txid": txid}

            else:
                response["error"] = {"code": RPC_DESERIALIZATION_ERROR, "message": "TX decode failed"}

        else:
            response["error"] = no_param_err
            response["error"]["message"] = response["error"]["message"].format("string")

    elif method == "sendrawtransaction":
        # TODO: A way of rejecting transactions should be added to test edge cases.
        txid = get_param(request_data)

        if isinstance(txid, str):
            if check_txid_format(txid):
                if txid not in list(mined_transactions.keys()):
                    mempool.append(txid)

                else:
                    response["error"] = {"code": RPC_VERIFY_ALREADY_IN_CHAIN,
                                         "message": "Transaction already in block chain"}

            else:
                response["error"] = {"code": RPC_DESERIALIZATION_ERROR, "message": "TX decode failed"}

        else:
            response["error"] = no_param_err
            response["error"]["message"] = response["error"]["message"].format("string")

    elif method == "getrawtransaction":
        txid = get_param(request_data)

        if isinstance(txid, str):
            block = blocks.get(mined_transactions.get(txid))

            if block:
                response["result"] = {"confirmations": len(blockchain) - block.get('height')}

            elif txid in mempool:
                response["result"] = {"confirmations": 0}

            else:
                response["error"] = {'code': RPC_INVALID_ADDRESS_OR_KEY,
                                     'message': 'No such mempool or blockchain transaction. Use gettransaction for '
                                                'wallet transactions.'}
        else:
            response["error"] = no_param_err
            response["error"]["message"] = response["error"]["message"].format("string")

    elif method == "getblockcount":
        response["result"] = len(blockchain)

    elif method == "getblock":
        blockid = get_param(request_data)

        if isinstance(blockid, str):
            block = blocks.get(blockid)

            if block:
                block["hash"] = blockid
                response["result"] = block

            else:
                response["error"] = {"code": RPC_INVALID_ADDRESS_OR_KEY, "message": "Block not found"}

        else:
            response["error"] = no_param_err
            response["error"]["message"] = response["error"]["message"].format("string")

    elif method == "getblockhash":
        height = get_param(request_data)

        if isinstance(height, int):
            if 0 <= height <= len(blockchain):
                response["result"] = blockchain[height]

            else:
                response["error"] = {"code": RPC_INVALID_PARAMETER, "message": "Block height out of range"}
        else:
            response["error"] = no_param_err
            response["error"]["message"] = response["error"]["message"].format("integer")

    elif method == "help":
        pass

    else:
        return abort(404, "Method not found")

    return Response(json.dumps(response), status=200, mimetype='application/json')


def get_param(request_data):
    param = None

    params = request_data.get("params")
    if isinstance(params, list) and len(params) > 0:
        param = params[0]

    return param


def load_data():
    pass


def simulate_mining():
    global mempool, mined_transactions, blocks, blockchain
    prev_block_hash = None

    while True:
        block_hash = os.urandom(32).hex()
        coinbase_tx_hash = os.urandom(32).hex()
        txs_to_mine = [coinbase_tx_hash]

        if len(mempool) != 0:
            # We'll mine up to 100 txs per block
            txs_to_mine += mempool[:99]
            mempool = mempool[99:]

        # Keep track of the mined transaction (to respond to getrawtransaction)
        for tx in txs_to_mine:
            mined_transactions[tx] = block_hash

        blocks[block_hash] = {"tx": txs_to_mine, "height": len(blockchain), "previousblockhash": prev_block_hash}
        mining_simulator.publish_data(binascii.unhexlify(block_hash))
        blockchain.append(block_hash)
        prev_block_hash = block_hash

        print("New block mined: {}".format(block_hash))
        print("\tTransactions: {}".format(txs_to_mine))

        time.sleep(TIME_BETWEEN_BLOCKS)


def run_simulator():
    mining_thread = Thread(target=simulate_mining)
    mining_thread.start()

    # Setting Flask log to ERROR only so it does not mess with out logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    app.run(host=HOST, port=PORT)
