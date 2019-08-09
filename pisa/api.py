from pisa import *
from pisa.watcher import Watcher
from pisa.inspector import Inspector
from pisa.appointment import Appointment
from flask import Flask, request, Response, abort, jsonify
import json


# FIXME: HERE FOR TESTING (get_block_count). REMOVE WHEN REMOVING THE FUNCTION
from pisa.utils.authproxy import AuthServiceProxy
from pisa.conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT

# ToDo: #5-add-async-to-api
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
            response = "appointment accepted. locator: {}".format(appointment.locator)
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


# FIXME: THE NEXT THREE API ENDPOINTS ARE FOR TESTING AND SHOULD BE REMOVED / PROPERLY MANAGED BEFORE PRODUCTION!
@app.route('/get_appointment', methods=['GET'])
def get_appointment():
    locator = request.args.get('locator')
    response = []

    appointment_in_watcher = watcher.appointments.get(locator)

    if appointment_in_watcher:
        for appointment in appointment_in_watcher:
            appointment_data = appointment.to_json()
            appointment_data['status'] = "being_watched"
            response.append(appointment_data)

    if watcher.responder:
        responder_jobs = watcher.responder.jobs

        for job_id, job in responder_jobs.items():
            if job.locator == locator:
                job_data = job.to_json()
                job_data['status'] = "dispute_responded"
                job_data['confirmations'] = watcher.responder.confirmation_counter.get(job_id)
                response.append(job_data)

    if not response:
        response.append({"locator": locator, "status": "not found"})

    response = jsonify(response)

    return response


@app.route('/get_all_appointments', methods=['GET'])
def get_all_appointments():
    watcher_appointments = []
    responder_jobs = []

    if request.remote_addr in request.host or request.remote_addr == '127.0.0.1':
        for app_id, appointment in watcher.appointments.items():
            jobs_data = [job.to_json() for job in appointment]

            watcher_appointments.append({app_id: jobs_data})

        if watcher.responder:
            for job_id, job in watcher.responder.jobs.items():
                job_data = job.to_json()
                job_data['confirmations'] = watcher.responder.confirmation_counter.get(job_id)
                responder_jobs.append({job_id: job_data})

        response = jsonify({"watcher_appointments": watcher_appointments, "responder_jobs": responder_jobs})

    else:
        abort(404)

    return response


@app.route('/get_block_count', methods=['GET'])
def get_block_count():
    bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                           BTC_RPC_PORT))

    return jsonify({"block_count": bitcoin_cli.getblockcount()})


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
