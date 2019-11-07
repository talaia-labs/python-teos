import os
import json
from flask import Flask, request, abort, jsonify
from binascii import hexlify

from pisa import HOST, PORT, logging
from pisa.logger import Logger
from pisa.inspector import Inspector
from pisa.appointment import Appointment
from pisa.block_processor import BlockProcessor


# ToDo: #5-add-async-to-api
app = Flask(__name__)

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_SERVICE_UNAVAILABLE = 503

logger = Logger("API")

watcher = None


@app.route("/", methods=["POST"])
def add_appointment():
    remote_addr = request.environ.get("REMOTE_ADDR")
    remote_port = request.environ.get("REMOTE_PORT")

    logger.info("Connection accepted", from_addr_port="{}:{}".format(remote_addr, remote_port))

    # Check content type once if properly defined
    request_data = json.loads(request.get_json())
    inspector = Inspector()
    appointment = inspector.inspect(
        request_data.get("appointment"), request_data.get("signature"), request_data.get("public_key")
    )

    error = None
    response = None

    if type(appointment) == Appointment:
        appointment_added, signature = watcher.add_appointment(appointment)

        if appointment_added:
            rcode = HTTP_OK
            response = {"locator": appointment.locator, "signature": hexlify(signature).decode("utf-8")}
        else:
            rcode = HTTP_SERVICE_UNAVAILABLE
            error = "appointment rejected"

    elif type(appointment) == tuple:
        rcode = HTTP_BAD_REQUEST
        error = "appointment rejected. Error {}: {}".format(appointment[0], appointment[1])

    else:
        # We  should never end up here, since inspect only returns appointments or tuples. Just in case.
        rcode = HTTP_BAD_REQUEST
        error = "appointment rejected. Request does not match the standard"

    logger.info(
        "Sending response and disconnecting",
        from_addr_port="{}:{}".format(remote_addr, remote_port),
        response=response,
        error=error,
    )

    if error is None:
        return jsonify(response), rcode
    else:
        return jsonify({"error": error}), rcode


# FIXME: THE NEXT THREE API ENDPOINTS ARE FOR TESTING AND SHOULD BE REMOVED / PROPERLY MANAGED BEFORE PRODUCTION!
# ToDo: #17-add-api-keys
@app.route("/get_appointment", methods=["GET"])
def get_appointment():
    locator = request.args.get("locator")
    response = []

    # ToDo: #15-add-system-monitor

    appointment_in_watcher = watcher.locator_uuid_map.get(locator)

    if appointment_in_watcher:
        for uuid in appointment_in_watcher:
            appointment_data = watcher.appointments[uuid].to_dict()
            appointment_data["status"] = "being_watched"
            response.append(appointment_data)

    if watcher.responder:
        responder_jobs = watcher.responder.jobs

        for job in responder_jobs.values():
            if job.locator == locator:
                job_data = job.to_dict()
                job_data["status"] = "dispute_responded"
                response.append(job_data)

    if not response:
        response.append({"locator": locator, "status": "not_found"})

    response = jsonify(response)

    return response


@app.route("/get_all_appointments", methods=["GET"])
def get_all_appointments():
    watcher_appointments = {}
    responder_jobs = {}

    # ToDo: #15-add-system-monitor

    if request.remote_addr in request.host or request.remote_addr == "127.0.0.1":
        for uuid, appointment in watcher.appointments.items():
            watcher_appointments[uuid] = appointment.to_dict()

        if watcher.responder:
            for uuid, job in watcher.responder.jobs.items():
                responder_jobs[uuid] = job.to_dict()

        response = jsonify({"watcher_appointments": watcher_appointments, "responder_jobs": responder_jobs})

    else:
        abort(404)

    return response


@app.route("/get_block_count", methods=["GET"])
def get_block_count():
    return jsonify({"block_count": BlockProcessor.get_block_count()})


def start_api(w):
    # FIXME: Pretty ugly but I haven't found a proper way to pass it to add_appointment
    global watcher

    # ToDo: #18-separate-api-from-watcher
    watcher = w

    # Setting Flask log to ERROR only so it does not mess with out logging. Also disabling flask initial messages
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    os.environ["WERKZEUG_RUN_MAIN"] = "true"

    app.run(host=HOST, port=PORT)
