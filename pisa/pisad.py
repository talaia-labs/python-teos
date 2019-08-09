import logging
from sys import argv
from getopt import getopt
from threading import Thread
from pisa.api import start_api
from pisa.tools import can_connect_to_bitcoind, in_correct_network
from pisa.utils.authproxy import AuthServiceProxy
from pisa.conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT, BTC_NETWORK, SERVER_LOG_FILE


if __name__ == '__main__':
    debug = False
    opts, _ = getopt(argv[1:], 'd', ['debug'])
    for opt, arg in opts:
        if opt in ['-d', '--debug']:
            debug = True

    # Configure logging
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO, handlers=[
        logging.FileHandler(SERVER_LOG_FILE),
        logging.StreamHandler()
    ])

    bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                           BTC_RPC_PORT))

    if can_connect_to_bitcoind(bitcoin_cli):
        if in_correct_network(bitcoin_cli, BTC_NETWORK):
            api_thread = Thread(target=start_api, args=[debug, logging])
            api_thread.start()
        else:
            logging.error("[Pisad] bitcoind is running on a different network, check conf.py and bitcoin.conf. "
                          "Shutting down")
    else:
        logging.error("[Pisad] can't connect to bitcoind. Shutting down")
