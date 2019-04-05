import logging
from sys import argv
from getopt import getopt
from conf import LOG_FILE
from threading import Thread
from pisa.api import manage_api


if __name__ == '__main__':
    debug = False
    opts, _ = getopt(argv[1:], 'd', ['debug'])
    for opt, arg in opts:
        if opt in ['-d', '--debug']:
            debug = True

    # Configure logging
    logging.basicConfig(format='%(asctime)s %(name)s: %(message)s', level=logging.INFO, handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ])

    api_thread = Thread(target=manage_api, args=[debug, logging])
    api_thread.start()
