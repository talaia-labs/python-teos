import json
from flask import Flask, request, Response, abort, jsonify

from pisa.watcher import Watcher
from pisa.inspector import Inspector
from pisa.appointment import Appointment
from pisa import HOST, PORT, logging, bitcoin_cli

# ToDo: #5-add-async-to-api
app = Flask(__name__)
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_SERVICE_UNAVAILABLE = 503


@app.route('/', methods=['POST'])
def add_appointment():
    remote_addr = request.environ.get('REMOTE_ADDR')
    remote_port = request.environ.get('REMOTE_PORT')

    logging.info('[API] connection accepted from {}:{}'.format(remote_addr, remote_port))

    # Check content type once if properly defined
    request_data = json.loads(request.get_json())
    appointment = inspector.inspect(request_data)

    if type(appointment) == Appointment:
        appointment_added = watcher.add_appointment(appointment)

        # ToDo: #13-create-server-side-signature-receipt
        if appointment_added:
            rcode = HTTP_OK
            response = "appointment accepted. locator: {}".format(appointment.locator)
        else:
            rcode = HTTP_SERVICE_UNAVAILABLE
            response = "appointment rejected"

    elif type(appointment) == tuple:
        rcode = HTTP_BAD_REQUEST
        response = "appointment rejected. Error {}: {}".format(appointment[0], appointment[1])

    else:
        # We  should never end up here, since inspect only returns appointments or tuples. Just in case.
        rcode = HTTP_BAD_REQUEST
        response = "appointment rejected. Request does not match the standard"

    logging.info('[API] sending response and disconnecting: {} --> {}:{}'.format(response, remote_addr, remote_port))

    return Response(response, status=rcode, mimetype='text/plain')


# FIXME: THE NEXT THREE API ENDPOINTS ARE FOR TESTING AND SHOULD BE REMOVED / PROPERLY MANAGED BEFORE PRODUCTION!
# ToDo: #17-add-api-keys
@app.route('/get_appointment', methods=['GET'])
def get_appointment():
    locator = request.args.get('locator')
    response = []

    # ToDo: #15-add-system-monitor

    appointment_in_watcher = watcher.locator_uuid_map.get(locator)

    if appointment_in_watcher:
        for uuid in appointment_in_watcher:
            appointment_data = watcher.appointments[uuid].to_json()
            appointment_data['status'] = "being_watched"
            response.append(appointment_data)

    if watcher.responder:
        responder_jobs = watcher.responder.jobs

        for job in responder_jobs.values():
            if job.locator == locator:
                job_data = job.to_json()
                job_data['status'] = "dispute_responded"
                response.append(job_data)

    if not response:
        response.append({"locator": locator, "status": "not found"})

    response = jsonify(response)

    return response


@app.route('/get_all_appointments', methods=['GET'])
def get_all_appointments():
    watcher_appointments = {}
    responder_jobs = {}

    # ToDo: #15-add-system-monitor

    if request.remote_addr in request.host or request.remote_addr == '127.0.0.1':
        for uuid, appointment in watcher.appointments.items():
            watcher_appointments[uuid] = appointment.to_json()

        if watcher.responder:
            for uuid, job in watcher.responder.jobs.items():
                responder_jobs[uuid] = job.to_json()

        response = jsonify({"watcher_appointments": watcher_appointments, "responder_jobs": responder_jobs})

    else:
        abort(404)

    return response


@app.route('/get_block_count', methods=['GET'])
def get_block_count():
    return jsonify({"block_count": bitcoin_cli.getblockcount()})


def start_api():
    # FIXME: Pretty ugly but I haven't found a proper way to pass it to add_appointment
    global watcher, inspector

    # ToDo: #18-separate-api-from-watcher
    watcher = Watcher()
    inspector = Inspector()

    # Setting Flask log t ERROR only so it does not mess with out logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    app.run(host=HOST, port=PORT)
