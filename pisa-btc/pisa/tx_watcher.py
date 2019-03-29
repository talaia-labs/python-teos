from pisa import shared
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT


def watch_txs(debug):
    bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT))

    while True:
        block_hash = shared.block_queue.get()

        try:
            block = bitcoin_cli.getblock(block_hash)

            prev_tx_id = block.get('previousblockhash')
            txs = block.get('tx')

            if debug:
                # Log shit
                print(prev_tx_id, txs)

        except JSONRPCException as e:
            print(e)
