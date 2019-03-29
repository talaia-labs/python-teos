import threading
from multiprocessing.connection import Listener
from pisa import *


def manage_api(debug, host=HOST, port=PORT):
    listener = Listener((host, port))
    while True:
        conn = listener.accept()

        if debug:
            print('Connection accepted from', listener.last_accepted)

        # Maintain metadata up to date.
        t_serve = threading.Thread(target=serve_data, args=[debug, conn, listener.last_accepted])
        t_serve.start()


def serve_data(debug, conn, remote_addr):
    while not conn.closed:
        try:
            msg = conn.recv()

            if type(msg) == tuple:
                if len(msg) is 2:
                    command, arg = msg

                    print(command, arg)

        except (IOError, EOFError):
            if debug:
                print('Disconnecting from', remote_addr)

            conn.close()
