import logging
from sys import argv
from getopt import getopt
from conf import SERVER_LOG_FILE
from threading import Thread
from pisa.api import start_api


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

    api_thread = Thread(target=start_api, args=[debug, logging])
    api_thread.start()
