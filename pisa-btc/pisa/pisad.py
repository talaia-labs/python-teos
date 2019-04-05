from getopt import getopt
from sys import argv
from threading import Thread
from pisa import shared
from pisa.api import manage_api


if __name__ == '__main__':
    debug = False
    opts, _ = getopt(argv[1:], 'd', ['debug'])
    for opt, arg in opts:
        if opt in ['-d', '--debug']:
            debug = True

    shared.init()

    api_thread = Thread(target=manage_api, args=[debug])
    api_thread.start()
