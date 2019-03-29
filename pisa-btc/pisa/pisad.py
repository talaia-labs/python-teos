from getopt import getopt
from sys import argv
from threading import Thread
from pisa import shared
from pisa.zmq_subscriber import run_subscribe
from pisa.tx_watcher import watch_txs
from pisa.api import manage_api


if __name__ == '__main__':
    debug = False
    opts, _ = getopt(argv[1:], 'd', ['debug'])
    for opt, arg in opts:
        if opt in ['-d', '--debug']:
            debug = True

    shared.init()

    zmq_thread = Thread(target=run_subscribe, args=[debug])
    tx_watcher_thread = Thread(target=watch_txs, args=[debug])
    api_thread = Thread(target=manage_api, args=[debug])

    zmq_thread.start()
    tx_watcher_thread.start()
    api_thread.start()
