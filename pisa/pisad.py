from getopt import getopt
from sys import argv, exit
from signal import signal, SIGINT, SIGQUIT, SIGTERM

from pisa.logger import Logger
from pisa.api import start_api
from pisa.conf import BTC_NETWORK
from pisa.tools import can_connect_to_bitcoind, in_correct_network

logger = Logger("Daemon")


def handle_signals(signal_received, frame):
    logger.info("Shutting down PISA")
    # TODO: #11-add-graceful-shutdown: add code to close the db, free any resources, etc.

    exit(0)


if __name__ == '__main__':
    logger.info("Starting PISA")

    signal(SIGINT, handle_signals)
    signal(SIGTERM, handle_signals)
    signal(SIGQUIT, handle_signals)

    opts, _ = getopt(argv[1:], '', [''])
    for opt, arg in opts:
        # FIXME: Leaving this here for future option/arguments
        pass

    if not can_connect_to_bitcoind():
        logger.error("Can't connect to bitcoind. Shutting down")

    elif not in_correct_network(BTC_NETWORK):
        logger.error("bitcoind is running on a different network, check conf.py and bitcoin.conf. Shutting down")

    else:
        # Fire the api
        start_api()
