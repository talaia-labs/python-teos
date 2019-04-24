import threading
from pisa import *
from pisa.watcher import Watcher
from pisa.inspector import Inspector
from multiprocessing.connection import Listener


def manage_api(debug, logging, host=HOST, port=PORT):
    listener = Listener((host, port))
    watcher = Watcher()
    inspector = Inspector()

    while True:
        conn = listener.accept()

        remote_addr, remote_port = listener.last_accepted

        if debug:
            logging.info('[API] connection accepted from {}:{}'.format(remote_addr, remote_port))

        # Maintain metadata up to date.
        t_serve = threading.Thread(target=manage_request, args=[conn, remote_addr, remote_port, inspector, watcher,
                                                                debug, logging])
        t_serve.start()


def manage_request(conn, remote_addr, remote_port, inspector, watcher, debug, logging):
    while not conn.closed:
        try:
            response = "Unknown command"
            msg = conn.recv()

            if type(msg) == tuple:
                if len(msg) is 2:
                    command, arg = msg

                    if command == "add_appointment":
                        appointment = inspector.inspect(arg, debug)
                        if appointment:
                            appointment_added = watcher.add_appointment(appointment, debug, logging)

                            if appointment_added:
                                response = "Appointment accepted"
                            else:
                                response = "Appointment rejected"
                        else:
                            response = "Appointment rejected"

            # Send response back. Change multiprocessing.connection for an http based connection
            if debug:
                logging.info('[API] sending response and disconnecting: {} --> {}:{}'.format(response, remote_addr,
                                                                                             remote_port))
            conn.close()

        except (IOError, EOFError):
            if debug:
                logging.info('[API] disconnecting from {}:{}'.format(remote_addr, remote_port))

            conn.close()
