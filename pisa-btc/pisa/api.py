from pisa import *
from pisa.watcher import Watcher
from pisa.inspector import Inspector
from pisa.appointment import Appointment
from flask import Flask, request, Response
import json

app = Flask(__name__)
HTTP_OK = 200
HTTP_BAD_REQUEST = 400


@app.route('/', methods=['POST'])
def add_appointment():
    remote_addr = request.environ.get('REMOTE_ADDR')
    remote_port = request.environ.get('REMOTE_PORT')

    if debug:
        logging.info('[API] connection accepted from {}:{}'.format(remote_addr, remote_port))

    # Check content type once if properly defined
    request_data = json.loads(request.get_json())
    appointment = inspector.inspect(request_data)

    if type(appointment) == Appointment:
        appointment_added = watcher.add_appointment(appointment, debug, logging)
        rcode = HTTP_OK

        # FIXME: Response should be signed receipt (created and signed by the API)
        if appointment_added:
            response = "appointment accepted"
        else:
            response = "appointment rejected"
            # FIXME: change the response code maybe?

    elif type(appointment) == tuple:
        rcode = HTTP_BAD_REQUEST
        response = "appointment rejected. Error {}: {}".format(appointment[0], appointment[1])
    else:

        rcode = HTTP_BAD_REQUEST
        response = "appointment rejected. Request does not match the standard"

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
    inspector = Inspector(debug, logging)

    # Setting Flask log t ERROR only so it does not mess with out logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    app.run(host=HOST, port=PORT)
