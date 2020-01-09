import os
import json
from flask import Flask, request, abort, jsonify

from pisa import HOST, PORT, logging
from common.logger import Logger
from pisa.inspector import Inspector
from common.appointment import Appointment
from pisa.block_processor import BlockProcessor

from common.constants import HTTP_OK, HTTP_BAD_REQUEST, HTTP_SERVICE_UNAVAILABLE, LOCATOR_LEN_HEX


# ToDo: #5-add-async-to-api
app = Flask(__name__)
logger = Logger("API")


class API:
    def __init__(self, watcher):
        self.watcher = watcher

    def add_appointment(self):
        """
        Main endpoint of the Watchtower.

        The client sends requests (appointments) to this endpoint to request a job to the Watchtower. Requests must be json
        encoded and contain an ``appointment`` field and optionally a ``signature`` and ``public_key`` fields.

        Returns:
            :obj:`tuple`: A tuple containing the response (``json``) and response code (``int``). For accepted appointments,
            the ``rcode`` is always 0 and the response contains the signed receipt. For rejected appointments, the ``rcode``
            is a negative value and the response contains the error message. Error messages can be found at
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
    def get_appointment(self):
        """
        Gives information about a given appointment state in the Watchtower.

        The information is requested by ``locator``.

        Returns:
            :obj:`dict`: A json formatted dictionary containing information about the requested appointment.

            A ``status`` flag is added to the data provided by either the :obj:`Watcher <pisa.watcher.Watcher>` or the
            :obj:`Responder <pisa.responder.Responder>` that signals the status of the appointment.

            - Appointments hold by the :obj:`Watcher <pisa.watcher.Watcher>` are flagged as ``being_watched``.
            - Appointments hold by the :obj:`Responder <pisa.responder.Responder>` are flagged as ``dispute_triggered``.
            - Unknown appointments are flagged as ``not_found``.
        """

        locator = request.args.get("locator")
        response = []

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
            :obj:`Watcher <pisa.watcher.Watcher>` (``watcher_appointments``) and by the
            :obj:`Responder <pisa.responder.Responder>` (``responder_trackers``).

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

    @staticmethod
    def get_block_count():
        """
        Provides the block height of the Watchtower.

        This is a testing endpoint that (most likely) will be removed in production. Its purpose is to give information to
        testers about the current block so they can define a dummy appointment without having to run a bitcoin node.

        Returns:
            :obj:`dict`: A json encoded dictionary containing the block height.

        """

        return jsonify({"block_count": BlockProcessor.get_block_count()})

    def start(self):
        """
        This function starts the Flask server used to run the API. Adds all the routes to the functions listed above.
        """

        routes = {
            "/": (self.add_appointment, ["POST"]),
            "/get_appointment": (self.get_appointment, ["GET"]),
            "/get_all_appointments": (self.get_all_appointments, ["GET"]),
            "/get_block_count": (self.get_block_count, ["GET"]),
        }

        for url, params in routes.items():
            app.add_url_rule(url, view_func=params[0], methods=params[1])

        # Setting Flask log to ERROR only so it does not mess with out logging. Also disabling flask initial messages
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        os.environ["WERKZEUG_RUN_MAIN"] = "true"

        app.run(host=HOST, port=PORT)
