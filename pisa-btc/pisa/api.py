from pisa import *
from pisa.watcher import Watcher
from pisa.inspector import Inspector
from flask import Flask, request, Response
import json

app = Flask(__name__)


@app.route('/', methods=['POST'])
def add_appointment():
    remote_addr = request.environ.get('REMOTE_ADDR')
    remote_port = request.environ.get('REMOTE_PORT')

    if debug:
        logging.info('[API] connection accepted from {}:{}'.format(remote_addr, remote_port))

    # Check content type once if properly defined
    # FIXME: Temporary patch until Paddy set's the client properly
    request_data = json.loads(request.form['data'])
    appointment = inspector.inspect(request_data, debug)

    if appointment:
        appointment_added = watcher.add_appointment(appointment, debug, logging)
        rcode = 200

        # FIXME: Response should be signed receipt (created and signed by the API)
        if appointment_added:
            response = "Appointment accepted"
        else:
            response = "Appointment rejected"
            # FIXME: change the response code maybe?

    else:
        rcode = 400
        response = "Appointment rejected. Request does not match the standard"

    # Send response back. Change multiprocessing.connection for an http based connection
    if debug:
        logging.info('[API] sending response and disconnecting: {} --> {}:{}'.format(response, remote_addr,
                                                                                     remote_port))

    return Response(response, status=rcode, mimetype='text/plain')


def start_api(d, l):
    # FIXME: Pretty ugly but I haven't found a proper way to pass it to add_appointment
    global debug, logging, watcher, inspector
    debug = d
    logging = l
    watcher = Watcher()
    inspector = Inspector()

    # Setting Flask log t ERROR only so it does not mess with out logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    app.run(host=HOST, port=PORT)
