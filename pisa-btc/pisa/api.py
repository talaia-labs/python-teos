import threading
from pisa import *
from pisa.watcher import Watcher
from pisa.inspector import Inspector
from multiprocessing.connection import Listener


def manage_api(debug, host=HOST, port=PORT):
    listener = Listener((host, port))
    watcher = Watcher()
    inspector = Inspector()

    while True:
        conn = listener.accept()

        if debug:
            print('Connection accepted from', listener.last_accepted)

        # Maintain metadata up to date.
        t_serve = threading.Thread(target=manage_request, args=[conn, listener.last_accepted, inspector, watcher,
                                                                debug])
        t_serve.start()


def manage_request(conn, remote_addr, inspector, watcher, debug):
    while not conn.closed:
        try:
            response = "Unknown command"
            msg = conn.recv()

            if type(msg) == tuple:
                if len(msg) is 2:
                    command, arg = msg

                    if command == "add_appointment":
                        appointment = inspector.inspect(msg, debug)
                        if appointment:
                            appointment_added = watcher.add_appointment(appointment, debug)

                            if appointment_added:
                                response = "Appointment accepted"
                            else:
                                response = "Appointment rejected"
                        else:
                            response = "Appointment rejected"

            # Send response back. Change multiprocessing.connection for an http based connection
            if debug:
                print('Sending response and disconnecting:', response, remote_addr)
            conn.close()

        except (IOError, EOFError):
            if debug:
                print('Disconnecting from', remote_addr)

            conn.close()
