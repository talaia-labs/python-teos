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
    if not isinstance(locator, str) or len(locator) != 64:
        response.append({"locator": locator, "status": "not_found"})
        return jsonify(response)

    locator_map = watcher.db_manager.load_locator_map(locator)

    if locator_map is not None:
        for uuid in locator_map:
            appointment_data = watcher.db_manager.load_watcher_appointment(uuid)

            if appointment_data is not None and appointment_data["triggered"] is False:
                # Triggered is an internal flag that does not need to be send
                del appointment_data["triggered"]

                appointment_data["status"] = "being_watched"
                response.append(appointment_data)

            job_data = watcher.db_manager.load_responder_job(uuid)

            if job_data is not None:
                job_data["status"] = "dispute_responded"
                response.append(job_data)

    else:
        response.append({"locator": locator, "status": "not_found"})

    response = jsonify(response)

    return response


@app.route("/get_all_appointments", methods=["GET"])
def get_all_appointments():
    # ToDo: #15-add-system-monitor
    response = None

    if request.remote_addr in request.host or request.remote_addr == "127.0.0.1":
        watcher_appointments = watcher.db_manager.load_watcher_appointments()
        responder_jobs = watcher.db_manager.load_responder_jobs()

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
