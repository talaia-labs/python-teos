import os
import json
import logging
from flask import Flask, request, abort, jsonify

from teos import HOST, PORT, LOG_PREFIX
from common.logger import Logger
from teos.inspector import Inspector
from common.appointment import Appointment

from common.constants import HTTP_OK, HTTP_BAD_REQUEST, HTTP_SERVICE_UNAVAILABLE, LOCATOR_LEN_HEX


# ToDo: #5-add-async-to-api
app = Flask(__name__)
logger = Logger(actor="API", log_name_prefix=LOG_PREFIX)


class API:
    def __init__(self, watcher, config):
        self.watcher = watcher
        self.config = config

    def add_appointment(self):
        """
        Main endpoint of the Watchtower.

        The client sends requests (appointments) to this endpoint to request a job to the Watchtower. Requests must be
        json encoded and contain an ``appointment`` field and optionally a ``signature`` and ``public_key`` fields.

        Returns:
            :obj:`tuple`: A tuple containing the response (``json``) and response code (``int``). For accepted
            appointments, the ``rcode`` is always 0 and the response contains the signed receipt. For rejected
            appointments, the ``rcode`` is a negative value and the response contains the error message. Error messages
            can be found at :mod:`Errors <teos.errors>`.
        """

        # Getting the real IP if the server is behind a reverse proxy
        remote_addr = request.environ.get("HTTP_X_REAL_IP")
        if not remote_addr:
            remote_addr = request.environ.get("REMOTE_ADDR")

        logger.info("Received add_appointment request", from_addr="{}".format(remote_addr))

        # FIXME: Logging every request so we can get better understanding of bugs in the alpha
        logger.debug("Request details", data="{}".format(request.data))

        if request.is_json:
            # Check content type once if properly defined
            request_data = json.loads(request.get_json())
            inspector = Inspector(self.config)
            appointment = inspector.inspect(
                request_data.get("appointment"), request_data.get("signature"), request_data.get("public_key")
            )

            error = None
            response = None

            if type(appointment) == Appointment:
                appointment_added, signature = self.watcher.add_appointment(appointment)

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

        else:
            rcode = HTTP_BAD_REQUEST
            error = "appointment rejected. Request is not json encoded"
            response = None

        logger.info(
            "Sending response and disconnecting", from_addr="{}".format(remote_addr), response=response, error=error
        )

        if error is None:
            return jsonify(response), rcode
        else:
            return jsonify({"error": error}), rcode

    # FIXME: THE NEXT TWO API ENDPOINTS ARE FOR TESTING AND SHOULD BE REMOVED / PROPERLY MANAGED BEFORE PRODUCTION!
    # ToDo: #17-add-api-keys
    def get_appointment(self):
        """
        Gives information about a given appointment state in the Watchtower.

        The information is requested by ``locator``.

        Returns:
            :obj:`dict`: A json formatted dictionary containing information about the requested appointment.

            A ``status`` flag is added to the data provided by either the :obj:`Watcher <teos.watcher.Watcher>` or the
            :obj:`Responder <teos.responder.Responder>` that signals the status of the appointment.

            - Appointments hold by the :obj:`Watcher <teos.watcher.Watcher>` are flagged as ``being_watched``.
            - Appointments hold by the :obj:`Responder <teos.responder.Responder>` are flagged as ``dispute_triggered``.
            - Unknown appointments are flagged as ``not_found``.
        """

        # Getting the real IP if the server is behind a reverse proxy
        remote_addr = request.environ.get("HTTP_X_REAL_IP")
        if not remote_addr:
            remote_addr = request.environ.get("REMOTE_ADDR")

        locator = request.args.get("locator")
        response = []

        logger.info("Received get_appointment request", from_addr="{}".format(remote_addr), locator=locator)

        # ToDo: #15-add-system-monitor
        if not isinstance(locator, str) or len(locator) != LOCATOR_LEN_HEX:
            response.append({"locator": locator, "status": "not_found"})
            return jsonify(response)

        locator_map = self.watcher.db_manager.load_locator_map(locator)
        triggered_appointments = self.watcher.db_manager.load_all_triggered_flags()

        if locator_map is not None:
            for uuid in locator_map:
                if uuid not in triggered_appointments:
                    appointment_data = self.watcher.db_manager.load_watcher_appointment(uuid)

                    if appointment_data is not None:
                        appointment_data["status"] = "being_watched"
                        response.append(appointment_data)

                tracker_data = self.watcher.db_manager.load_responder_tracker(uuid)

                if tracker_data is not None:
                    tracker_data["status"] = "dispute_responded"
                    response.append(tracker_data)

        else:
            response.append({"locator": locator, "status": "not_found"})

        response = jsonify(response)

        return response

    def get_all_appointments(self):
        """
        Gives information about all the appointments in the Watchtower.

        This endpoint should only be accessible by the administrator. Requests are only allowed from localhost.

        Returns:
            :obj:`dict`: A json formatted dictionary containing all the appointments hold by the
            :obj:`Watcher <teos.watcher.Watcher>` (``watcher_appointments``) and by the
            :obj:`Responder <teos.responder.Responder>` (``responder_trackers``).

        """

        # ToDo: #15-add-system-monitor
        response = None

        if request.remote_addr in request.host or request.remote_addr == "127.0.0.1":
            watcher_appointments = self.watcher.db_manager.load_watcher_appointments()
            responder_trackers = self.watcher.db_manager.load_responder_trackers()

            response = jsonify({"watcher_appointments": watcher_appointments, "responder_trackers": responder_trackers})

        else:
            abort(404)

        return response

    def start(self):
        """
        This function starts the Flask server used to run the API. Adds all the routes to the functions listed above.
        """

        routes = {
            "/": (self.add_appointment, ["POST"]),
            "/get_appointment": (self.get_appointment, ["GET"]),
            "/get_all_appointments": (self.get_all_appointments, ["GET"]),
        }

        for url, params in routes.items():
            app.add_url_rule(url, view_func=params[0], methods=params[1])

        # Setting Flask log to ERROR only so it does not mess with out logging. Also disabling flask initial messages
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        os.environ["WERKZEUG_RUN_MAIN"] = "true"

        app.run(host=HOST, port=PORT)
