import os
import logging
from flask import Flask, request, abort, jsonify

from teos import LOG_PREFIX
import common.errors as errors
from teos.inspector import InspectionFailed
from teos.gatekeeper import NotEnoughSlots, AuthenticationFailure
from teos.watcher import AppointmentLimitReached, AppointmentAlreadyTriggered, AppointmentNotFound

from common.logger import Logger
from common.cryptographer import hash_160
from common.exceptions import InvalidParameter
from common.constants import HTTP_OK, HTTP_BAD_REQUEST, HTTP_SERVICE_UNAVAILABLE, HTTP_NOT_FOUND


# ToDo: #5-add-async-to-api
app = Flask(__name__)
logger = Logger(actor="API", log_name_prefix=LOG_PREFIX)


# NOTCOVERED: not sure how to monkey path this one. May be related to #77
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


# NOTCOVERED: not sure how to monkey path this one. May be related to #77
def get_request_data_json(request):
    """
    Gets the content of a json POST request and makes sure it decodes to a dictionary.

    Args:
        request (:obj:`Request`): the request sent by the user.

    Returns:
        :obj:`dict`: the dictionary parsed from the json request.

    Raises:
        :obj:`InvalidParameter`: if the request is not json encoded or it does not decodes to a dictionary.
    """

    if request.is_json:
        request_data = request.get_json()
        if isinstance(request_data, dict):
            return request_data
        else:
            raise InvalidParameter("Invalid request content")
    else:
        raise InvalidParameter("Request is not json encoded")


class API:
    """
    The :class:`API` is in charge of the interface between the user and the tower. It handles and serves user requests.

    Args:
        host (:obj:`str`): the hostname to listen on.
        port (:obj:`int`): the port of the webserver.
        inspector (:obj:`Inspector <teos.inspector.Inspector>`): an ``Inspector`` instance to check the correctness of
            the received appointment data.
        watcher (:obj:`Watcher <teos.watcher.Watcher>`): a ``Watcher`` instance to pass the requests to.
    """

    def __init__(self, host, port, inspector, watcher):
        self.host = host
        self.port = port
        self.inspector = inspector
        self.watcher = watcher
        self.app = app

        # Adds all the routes to the functions listed above.
        routes = {
            "/register": (self.register, ["POST"]),
            "/add_appointment": (self.add_appointment, ["POST"]),
            "/get_appointment": (self.get_appointment, ["POST"]),
            "/get_all_appointments": (self.get_all_appointments, ["GET"]),
            "/delete_appointment": (self.delete_appointment, ["POST"]),
        }

        for url, params in routes.items():
            app.add_url_rule(url, view_func=params[0], methods=params[1])

    def register(self):
        """
        Registers a user by creating a subscription.

        Registration is pretty straightforward for now, since it does not require payments.
        The amount of slots and expiry of the subscription cannot be requested by the user yet either. This is linked to
        the previous point.
        Users register by sending a public key to the proper endpoint. This is exploitable atm, but will be solved when
        payments are introduced.

        Returns:
            :obj:`tuple`: A tuple containing the response (:obj:`str`) and response code (:obj:`int`). For accepted
            requests, the ``rcode`` is always 200 and the response contains a json with the public key and number of
            slots in the subscription. For rejected requests, the ``rcode`` is a 404 and the value contains an
            application error, and an error message. Error messages can be found at :mod:`Errors <teos.errors>`.
        """

        remote_addr = get_remote_addr()
        logger.info("Received register request", from_addr="{}".format(remote_addr))

        # Check that data type and content are correct. Abort otherwise.
        try:
            request_data = get_request_data_json(request)

        except InvalidParameter as e:
            logger.info("Received invalid register request", from_addr="{}".format(remote_addr))
            return jsonify({"error": str(e), "error_code": errors.INVALID_REQUEST_FORMAT}), HTTP_BAD_REQUEST

        user_id = request_data.get("public_key")

        if user_id:
            try:
                rcode = HTTP_OK
                available_slots, subscription_expiry = self.watcher.gatekeeper.add_update_user(user_id)
                response = {
                    "public_key": user_id,
                    "available_slots": available_slots,
                    "subscription_expiry": subscription_expiry,
                }

            except InvalidParameter as e:
                rcode = HTTP_BAD_REQUEST
                response = {"error": str(e), "error_code": errors.REGISTRATION_MISSING_FIELD}

        else:
            rcode = HTTP_BAD_REQUEST
            response = {
                "error": "public_key not found in register message",
                "error_code": errors.REGISTRATION_WRONG_FIELD_FORMAT,
            }

        logger.info("Sending response and disconnecting", from_addr="{}".format(remote_addr), response=response)

        return jsonify(response), rcode

    def add_appointment(self):
        """
        Main endpoint of the Watchtower.

        The client sends requests (appointments) to this endpoint to request a job to the Watchtower. Requests must be
        json encoded and contain an ``appointment`` and ``signature`` fields.

        Returns:
            :obj:`tuple`: A tuple containing the response (:obj:`str`) and response code (:obj:`int`). For accepted
            appointments, the ``rcode`` is always 200 and the response contains the receipt signature (json). For
            rejected appointments, the ``rcode`` contains an application error, and an error message. Error messages can
            be found at :mod:`Errors <teos.errors>`.
        """

        # Getting the real IP if the server is behind a reverse proxy
        remote_addr = get_remote_addr()
        logger.info("Received add_appointment request", from_addr="{}".format(remote_addr))

        # Check that data type and content are correct. Abort otherwise.
        try:
            request_data = get_request_data_json(request)

        except InvalidParameter as e:
            return jsonify({"error": str(e), "error_code": errors.INVALID_REQUEST_FORMAT}), HTTP_BAD_REQUEST

        try:
            appointment = self.inspector.inspect(request_data.get("appointment"))
            response = self.watcher.add_appointment(appointment, request_data.get("signature"))
            rcode = HTTP_OK

        except InspectionFailed as e:
            rcode = HTTP_BAD_REQUEST
            response = {"error": "appointment rejected. {}".format(e.reason), "error_code": e.erno}

        except (AuthenticationFailure, NotEnoughSlots):
            rcode = HTTP_BAD_REQUEST
            response = {
                "error": "appointment rejected. Invalid signature or user does not have enough slots available",
                "error_code": errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS,
            }

        except AppointmentLimitReached:
            rcode = HTTP_SERVICE_UNAVAILABLE
            response = {"error": "appointment rejected"}

        except AppointmentAlreadyTriggered:
            rcode = HTTP_BAD_REQUEST
            response = {
                "error": "appointment rejected. The provided appointment has already been triggered",
                "error_code": errors.APPOINTMENT_ALREADY_TRIGGERED,
            }

        logger.info("Sending response and disconnecting", from_addr="{}".format(remote_addr), response=response)
        return jsonify(response), rcode

    def get_appointment(self):
        """
        Gives information about a given appointment state in the Watchtower.

        The information is requested by ``locator``.

        Returns:
            :obj:`str`: A json formatted dictionary containing information about the requested appointment.

            Returns not found if the user does not have the requested appointment or the locator is invalid.

            A ``status`` flag is added to the data provided by either the :obj:`Watcher <teos.watcher.Watcher>` or the
            :obj:`Responder <teos.responder.Responder>` that signals the status of the appointment.

            - Appointments hold by the :obj:`Watcher <teos.watcher.Watcher>` are flagged as ``being_watched``.
            - Appointments hold by the :obj:`Responder <teos.responder.Responder>` are flagged as ``dispute_triggered``.
            - Unknown appointments are flagged as ``not_found``.
        """

        # Getting the real IP if the server is behind a reverse proxy
        remote_addr = get_remote_addr()

        # Check that data type and content are correct. Abort otherwise.
        try:
            request_data = get_request_data_json(request)

        except InvalidParameter as e:
            logger.info("Received invalid get_appointment request", from_addr="{}".format(remote_addr))
            return jsonify({"error": str(e), "error_code": errors.INVALID_REQUEST_FORMAT}), HTTP_BAD_REQUEST

        locator = request_data.get("locator")

        try:
            self.inspector.check_locator(locator)
            logger.info("Received get_appointment request", from_addr="{}".format(remote_addr), locator=locator)

            message = "get appointment {}".format(locator).encode()
            signature = request_data.get("signature")
            user_id = self.watcher.gatekeeper.authenticate_user(message, signature)

            triggered_appointments = self.watcher.db_manager.load_all_triggered_flags()
            uuid = hash_160("{}{}".format(locator, user_id))

            # If the appointment has been triggered, it should be in the locator (default else just in case).
            if uuid in triggered_appointments:
                appointment_data = self.watcher.db_manager.load_responder_tracker(uuid)
                if appointment_data:
                    rcode = HTTP_OK
                    # Remove user_id field from appointment data since it is an internal field
                    appointment_data.pop("user_id")
                    response = {"locator": locator, "status": "dispute_responded", "appointment": appointment_data}
                else:
                    rcode = HTTP_NOT_FOUND
                    response = {"locator": locator, "status": "not_found"}

            # Otherwise it should be either in the watcher, or not in the system.
            else:
                appointment_data = self.watcher.db_manager.load_watcher_appointment(uuid)
                if appointment_data:
                    rcode = HTTP_OK
                    # Remove user_id field from appointment data since it is an internal field
                    appointment_data.pop("user_id")
                    response = {"locator": locator, "status": "being_watched", "appointment": appointment_data}
                else:
                    rcode = HTTP_NOT_FOUND
                    response = {"locator": locator, "status": "not_found"}

        except (InspectionFailed, AuthenticationFailure):
            rcode = HTTP_NOT_FOUND
            response = {"locator": locator, "status": "not_found"}

        return jsonify(response), rcode

    def get_all_appointments(self):
        """
        Gives information about all the appointments in the Watchtower.

        This endpoint should only be accessible by the administrator. Requests are only allowed from localhost.

        Returns:
            :obj:`str`: A json formatted dictionary containing all the appointments hold by the ``Watcher``
            (``watcher_appointments``) and by the ``Responder>`` (``responder_trackers``).
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

    def delete_appointment(self):
        """
        Delete information about a given appointment state in the Watchtower.

        The information is requested by ``locator``.

        Returns:
            :obj:`str`: A json formatted dictionary containing information about the appointment deletion request.

            Returns not found if the user does not have the requested appointment or the locator is invalid.
            Returns bad request if the appointment does not exist in the Watchtower.

            A ``status`` flag is added to the data that signals the status of the deletion request.

            - A successfully deleted appointment is flagged as ``deletion_accepted``.
            - An appointment that did not exist (or was already deleted), or where the locator is invalid or the user
            does not have the requested appointment, are flagged as ``deletion_rejected``.

            :obj:`tuple`: A tuple containing the response (:obj:`str`) and response code (:obj:`int`). For accepted
            appointments, the ``rcode`` is always 200 and the response contains the receipt signature (json). For
            rejected appointments, the ``rcode`` is either 400 or 404:

            If the appointment is not found: 404
            If the request is invalid: 400
            If the appointment is already in the responder: 400 + message
        """

        # Getting the real IP if the server is behind a reverse proxy
        remote_addr = get_remote_addr()

        # Check that data type and content are correct. Abort otherwise.
        try:
            request_data = get_request_data_json(request)

        except InvalidParameter as e:
            logger.info("Received invalid delete_appointment request", from_addr="{}".format(remote_addr))
            return jsonify({"error": str(e), "error_code": errors.INVALID_REQUEST_FORMAT}), HTTP_BAD_REQUEST

        locator = request_data.get("locator")

        try:
            self.inspector.check_locator(locator)
            logger.info("Received delete_appointment request", from_addr=remote_addr, locator=locator)

            message = "delete appointment {}".format(locator).encode()
            user_signature = request_data.get("signature")
            user_id = self.watcher.gatekeeper.authenticate_user(message, user_signature)

            tower_signature = self.watcher.pop_appointment(locator, user_id, user_signature)

            rcode = HTTP_OK
            response = {
                "locator": locator,
                "signature": tower_signature,
                "available_slots": self.watcher.gatekeeper.registered_users[user_id].get("available_slots"),
                "status": "deletion_accepted",
            }

        except AppointmentNotFound:
            rcode = HTTP_NOT_FOUND
            response = {"locator": locator, "status": "deletion_rejected"}

        except AppointmentAlreadyTriggered as e:
            rcode = HTTP_BAD_REQUEST
            response = {"locator": locator, "status": "deletion_rejected", "error": e.msg}

        except (InspectionFailed, AuthenticationFailure):
            rcode = HTTP_BAD_REQUEST
            response = {"locator": locator, "status": "deletion_rejected"}

        return jsonify(response), rcode

    def start(self):
        """ This function starts the Flask server used to run the API """

        # Setting Flask log to ERROR only so it does not mess with our logging. Also disabling flask initial messages
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        os.environ["WERKZEUG_RUN_MAIN"] = "true"

        app.run(host=self.host, port=self.port)
