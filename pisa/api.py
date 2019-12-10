import os
import json
from flask import Flask, request, abort, jsonify

from pisa import HOST, PORT, logging
from pisa.logger import Logger
from pisa.inspector import Inspector
from pisa.appointment import Appointment
from pisa.block_processor import BlockProcessor

from common.constants import HTTP_OK, HTTP_BAD_REQUEST, HTTP_SERVICE_UNAVAILABLE, LOCATOR_LEN_HEX


# ToDo: #5-add-async-to-api
app = Flask(__name__)
logger = Logger("API")
watcher = None


@app.route("/", methods=["POST"])
def add_appointment():
    """
    Add appointment endpoint, it is used as the main endpoint of the Watchtower.

    The client sends requests (appointments) to this endpoint to request a job to the Watchtower. Requests must be json
    encoded and contain an ``appointment`` field and optionally a ``signature`` and ``public_key`` fields.

    Returns:
        ``tuple``: A tuple containing the response (``json``) and response code (``int``). For accepted appointments, the
        ``rcode`` is always 0 and the response contains the signed receipt. For rejected appointments, the ``rcode`` is
        a negative value and the response contains the error message. Error messages can be found at
        :mod:`Errors <pisa.errors>`.
    """

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
            response = {"locator": appointment.locator, "signature": signature}

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
    """
    Get appointment endpoint, it gives information about a given appointment state in the Watchtower.

    The information is requested by ``locator``.

    Returns:
        ``dict``: A json formatted dictionary containing information about the requested appointment.

        A ``status`` flag is added to the data provided by either the :mod:`Watcher <pisa.watcher>` or the
        :mod:`Responder <pisa.responder>` that signals the status of the appointment.

        - Appointments hold by the :mod:`Watcher <pisa.watcher>` are flagged as ``being_watched``.
        - Appointments hold by the :mod:`Responder <pisa.responder>` are flagged as ``dispute_triggered``.
        - Unknown appointments are flagged as ``not_found``.
    """

    locator = request.args.get("locator")
    response = []

    # ToDo: #15-add-system-monitor
    if not isinstance(locator, str) or len(locator) != LOCATOR_LEN_HEX:
        response.append({"locator": locator, "status": "not_found"})
        return jsonify(response)

    locator_map = watcher.db_manager.load_locator_map(locator)

    if locator_map is not None:
        for uuid in locator_map:
            appointment_data = watcher.db_manager.load_watcher_appointment(uuid)

            if appointment_data is not None and appointment_data["triggered"] is False:
                # Triggered is an internal flag
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
    """
    Get all appointments endpoint, it gives information about all the appointments in the Watchtower.

    This endpoint should only be accessible by the administrator. Requests are only allowed from localhost.

    Returns:
        ``dict``: A json formatted dictionary containing all the appointments hold by the :mod:`Watcher <pisa.watcher>`
        (``watcher_appointments``) and by the :mod:`Responder <pisa.responder>` (``responder_jobs``).

    """

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
    """
    Get block count endpoint, it provides the block height of the Watchtower.

    This is a testing endpoint that (most likely) will be removed in production. Its purpose is to give information to
    testers about the current block so they can define a dummy appointment without having to run a bitcoin node.

    Returns:
        ``dict``: A json encoded dictionary containing the block height.

    """

    return jsonify({"block_count": BlockProcessor.get_block_count()})


def start_api(w):
    """
    This function starts the Flask server used to run the API.

    Args:
          w (Watcher): A :mod:`Watcher <pisa.watcher>` object.

    """

    # FIXME: Pretty ugly but I haven't found a proper way to pass it to add_appointment
    global watcher

    # ToDo: #18-separate-api-from-watcher
    watcher = w

    # Setting Flask log to ERROR only so it does not mess with out logging. Also disabling flask initial messages
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    os.environ["WERKZEUG_RUN_MAIN"] = "true"

    app.run(host=HOST, port=PORT)
