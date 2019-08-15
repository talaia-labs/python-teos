from pisa.conf import FEED_PROTOCOL, FEED_ADDR, FEED_PORT
from flask import Flask, request, Response, abort
from tests.zmq_publisher import ZMQPublisher
from threading import Thread
import binascii
import json
import os
import time


app = Flask(__name__)
HOST = 'localhost'
PORT = '18443'


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

    getblock:               querying for a block will return a dictionary with a two fields: "tx" representing a list of
                            transactions, and "height" representing the block height. Both will be got from the mining
                            simulator.

    getblockhash:           a block hash is only queried by pisad on bootstrapping to check the network bitcoind is
                            running on. It always asks for the genesis block. Since this is ment to be for testing we
                            will return the testnet3 genesis block hash.

    help:                   help is only used as a sample command to test if bitcoind is running when bootstrapping
                            pisad. It will return a 200/OK with no data.
    """

    global sent_transactions
    request_data = request.get_json()
    method = request_data.get('method')

    response = {"id": 0, "result": 0, "error": None}

    if method == "decoderawtransaction":
        txid = get_param(request_data)

        if txid:
            response["result"] = {"txid": txid}

    elif method == "sendrawtransaction":
        txid = get_param(request_data)

        if txid:
            sent_transactions.append(txid)

        # FIXME: If the same transaction is sent twice it should return an error informing that the transaction is
        #        already known

    elif method == "getrawtransaction":
        txid = get_param(request_data)

        if txid:
            block = blocks.get(mined_transactions.get(txid))

            if block:
                response["result"] = {"confirmations": block_count - block.get('height')}

            else:
                # FIXME: if the transaction cannot be found it should return an error. Check bitcoind
                return abort(500)

    elif method == "getblockcount":
        response["result"] = block_count

    elif method == "getblock":
        blockid = get_param(request_data)

        if blockid:
            response["result"] = blocks.get(blockid)

    elif method == "getblockhash":
        height = get_param(request_data)
        if height == 0:
            # testnet3 genesis block hash
            response["result"] = "000000000933ea01ad0ee984209779baaec3ced90fa3f408719526f8d77f4943"

        else:
            return abort(500, "Unsupported method")

    elif method == "help":
        pass

    else:
        return abort(500, "Unsupported method")

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
    global sent_transactions, mined_transactions, blocks, block_count

    while True:
        block_hash = binascii.hexlify(os.urandom(32)).decode('utf-8')
        coinbase_tx_hash = binascii.hexlify(os.urandom(32)).decode('utf-8')
        txs_to_mine = [coinbase_tx_hash]

        if len(sent_transactions) != 0:
            # We'll mine up to 100 txs per block
            txs_to_mine += sent_transactions[:99]
            sent_transactions = sent_transactions[99:]

        # Keep track of the mined transaction (to respond to getrawtransaction)
        for tx in txs_to_mine:
            mined_transactions[tx] = block_hash

        blocks[block_hash] = {"tx": txs_to_mine, "height": block_count}
        mining_simulator.publish_data(binascii.unhexlify(block_hash))

        block_count += 1
        time.sleep(10)


if __name__ == '__main__':
    mining_simulator = ZMQPublisher(topic=b'hashblock', feed_protocol=FEED_PROTOCOL, feed_addr=FEED_ADDR,
                                    feed_port=FEED_PORT)

    sent_transactions = []
    mined_transactions = {}
    blocks = {}
    block_count = 0

    mining_thread = Thread(target=simulate_mining)
    mining_thread.start()

    app.run(host=HOST, port=PORT)
