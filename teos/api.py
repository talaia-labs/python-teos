import os
import logging
from math import ceil
from flask import Flask, request, abort, jsonify

import teos.errors as errors
from teos.gatekeeper import NotEnoughSlots
from teos import HOST, PORT, LOG_PREFIX

from common.logger import Logger
from common.appointment import Appointment
from common.constants import (
    HTTP_OK,
    HTTP_BAD_REQUEST,
    HTTP_SERVICE_UNAVAILABLE,
    LOCATOR_LEN_HEX,
    ENCRYPTED_BLOB_MAX_SIZE_HEX,
)


# ToDo: #5-add-async-to-api
app = Flask(__name__)
logger = Logger(actor="API", log_name_prefix=LOG_PREFIX)


# TODO: UNITTEST
def get_remote_addr():
    """
    Gets the remote client ip address. The HTTP_X_REAL_IP field is tried first in case the server is behind a reverse
     proxy.

    Returns:
        :obj:`str`: the IP address of the client.
    """

    # Getting the real IP if the server is behind a reverse proxy
    remote_addr = request.environ.get("HTTP_X_REAL_IP")
    if not remote_addr:
        remote_addr = request.environ.get("REMOTE_ADDR")

    return remote_addr


class API:
    # FIXME: DOCS
    """
    The :class:`API` is in charge of the interface between the user and the tower. It handles and server user requests.

    Args:
        inspector (:obj:`Inspector <teos.inspector.Inspector>`): an ``Inspector`` instance to check the correctness of
            the received data.
        watcher (:obj:`Watcher <teos.watcher.Watcher>`): a ``Watcher`` instance to pass the requests to.
    """

    # TODO: UNITTEST
    def __init__(self, inspector, watcher, gatekeeper):
        self.inspector = inspector
        self.watcher = watcher
        self.gatekeeper = gatekeeper

    # TODO: UNITTEST, DOCS
    def register(self):
        remote_addr = get_remote_addr()

        logger.info("Received register request", from_addr="{}".format(remote_addr))

        if request.is_json:
            request_data = request.get_json()
            client_pk = request_data.get("public_key")

            if client_pk:
                try:
                    rcode = HTTP_OK
                    available_slots = self.gatekeeper.add_update_user(client_pk)
                    response = {"public_key": client_pk, "available_slots": available_slots}

                except ValueError as e:
                    rcode = HTTP_BAD_REQUEST
                    error = "Error {}: {}".format(errors.REGISTRATION_MISSING_FIELD, str(e))
                    response = {"error": error}

            else:
                rcode = HTTP_BAD_REQUEST
                error = "Error {}: public_key not found in register message".format(
                    errors.REGISTRATION_WRONG_FIELD_FORMAT
                )
                response = {"error": error}

        else:
            rcode = HTTP_BAD_REQUEST
            error = "appointment rejected. Request is not json encoded"
            response = {"error": error}

        logger.info("Sending response and disconnecting", from_addr="{}".format(remote_addr), response=response)

        return jsonify(response), rcode

    # FIXME: UNITTEST
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
        remote_addr = get_remote_addr()

        logger.info("Received add_appointment request", from_addr="{}".format(remote_addr))

        if request.is_json:
            # Check content type once if properly defined
            request_data = request.get_json()
            user_pk = self.gatekeeper.identify_user(request_data.get("appointment"), request_data.get("signature"))

            if user_pk:
                appointment = self.inspector.inspect(request_data.get("appointment"))

                if type(appointment) == Appointment:
                    # An appointment will fill 1 slot per ENCRYPTED_BLOB_MAX_SIZE_HEX block.
                    required_slots = ceil(len(appointment.encrypted_blob.data) / ENCRYPTED_BLOB_MAX_SIZE_HEX)

                    # Temporarily taking out slots to avoid abusing this via race conditions
                    # DISCUSS: It may be worth using signals here to avoid race conditions anyway
                    try:
                        self.gatekeeper.fill_slots(user_pk, required_slots)

                        appointment_added, signature = self.watcher.add_appointment(appointment)

                        if appointment_added:
                            rcode = HTTP_OK
                            response = {"locator": appointment.locator, "signature": signature}

                        else:
                            # Adding back the slots since they were not used
                            self.gatekeeper.free_slots(user_pk, required_slots)
                            rcode = HTTP_SERVICE_UNAVAILABLE
                            error = "appointment rejected"
                            response = {"error": error}

                    except NotEnoughSlots:
                        # Adding back the slots since they were not used
                        self.gatekeeper.free_slots(user_pk, required_slots)
                        rcode = HTTP_BAD_REQUEST
                        error = "appointment rejected. Error {}: {}".format(
                            errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS,
                            "Invalid signature or the user does not have enough slots available",
                        )
                        response = {"error": error}

                elif type(appointment) == tuple:
                    rcode = HTTP_BAD_REQUEST
                    error = "appointment rejected. Error {}: {}".format(appointment[0], appointment[1])
                    response = {"error": error}

                else:
                    # We  should never end up here, since inspect only returns appointments or tuples. Just in case.
                    rcode = HTTP_BAD_REQUEST
                    error = "appointment rejected. Request does not match the standard"
                    response = {"error": error}

            else:
                rcode = HTTP_BAD_REQUEST
                error = "appointment rejected. Error {}: {}".format(
                    errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS,
                    "Invalid signature or the user does not have enough slots available",
                )
                response = {"error": error}

        else:
            rcode = HTTP_BAD_REQUEST
            error = "appointment rejected. Request is not json encoded"
            response = {"error": error}

        logger.info("Sending response and disconnecting", from_addr="{}".format(remote_addr), response=response)
        return jsonify(response), rcode

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
        remote_addr = get_remote_addr()

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

    # TODO: UNITTEST
    def start(self):
        """
        This function starts the Flask server used to run the API. Adds all the routes to the functions listed above.
        """

        routes = {
            "/register": (self.register, ["POST"]),
            "/add_appointment": (self.add_appointment, ["POST"]),
            "/get_appointment": (self.get_appointment, ["GET"]),
            "/get_all_appointments": (self.get_all_appointments, ["GET"]),
        }

        for url, params in routes.items():
            app.add_url_rule(url, view_func=params[0], methods=params[1])

        # Setting Flask log to ERROR only so it does not mess with out logging. Also disabling flask initial messages
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        os.environ["WERKZEUG_RUN_MAIN"] = "true"

        app.run(host=HOST, port=PORT)
