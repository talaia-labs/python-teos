from sys import argv, exit
from getopt import getopt
from signal import signal, SIGINT

from pisa.logger import Logger
from pisa.api import start_api
from pisa.tools import can_connect_to_bitcoind, in_correct_network

logger = Logger("Daemon")


def handle_sigint(signal_received, frame):
    print("Shutting down PISA...")
    # TODO: add code to close the db, free any resources, etc.

    exit(0)


if __name__ == '__main__':
    signal(SIGINT, handle_sigint)

    debug = False
    opts, _ = getopt(argv[1:], 'd', ['debug'])
    for opt, arg in opts:
        # FIXME: Leaving this here for future option/arguments
        pass

    if can_connect_to_bitcoind():
        if in_correct_network():
            # Fire the api
            start_api()

        else:
            logger.error("bitcoind is running on a different network, check conf.py and bitcoin.conf. Shutting down")

    else:
        logger.error("Can't connect to bitcoind. Shutting down")
