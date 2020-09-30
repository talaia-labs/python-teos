import grpc
from google.protobuf import json_format
from waitress import serve as wsgi_serve
from flask import Flask, request, jsonify


import common.errors as errors
from common.appointment import AppointmentStatus
from common.exceptions import InvalidParameter
from common.constants import HTTP_OK, HTTP_BAD_REQUEST, HTTP_SERVICE_UNAVAILABLE, HTTP_NOT_FOUND
from teos.inspector import Inspector, InspectionFailed
from teos.protobuf.user_pb2 import RegisterRequest
from teos.protobuf.tower_services_pb2_grpc import TowerServicesStub
from teos.protobuf.appointment_pb2 import Appointment, AddAppointmentRequest, GetAppointmentRequest

from teos.logger import setup_logging, get_logger


# NOTCOVERED: not sure how to monkey patch this one. May be related to #77
def get_remote_addr():
    """
    Gets the remote client ip address. The ``HTTP_X_REAL_IP`` field is tried first in case the server is behind a
    reverse proxy.

    Returns:
        :obj:`str`: The IP address of the client.
    """

    # Getting the real IP if the server is behind a reverse proxy
    remote_addr = request.environ.get("HTTP_X_REAL_IP")
    if not remote_addr:
        remote_addr = request.environ.get("REMOTE_ADDR")

    return remote_addr


# NOTCOVERED: not sure how to monkey patch this one. May be related to #77
def get_request_data_json(request):
    """
    Gets the content of a json ``POST`` request and makes sure it decodes to a dictionary.

    Args:
        request (:obj:`Request`): the request sent by the user.

    Returns:
        :obj:`dict`: The dictionary parsed from the json request.

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


def serve(internal_api_endpoint, endpoint, logging_port, min_to_self_delay, auto_run=False):
    """
    Starts the API.

    This method can be handled either form an external WSGI (like gunicorn) or by the Flask development server.

    Args:
        internal_api_endpoint (:obj:`str`): endpoint where the internal api is running (``host:port``).
        endpoint (:obj:`str`): endpoint where the http api will be running (``host:port``).
        logging_port (:obj:`int`): the port where the logging server can be reached (localhost:logging_port)
        min_to_self_delay (:obj:`str`): the minimum to_self_delay accepted by the :obj:`Inspector`.
        auto_run (:obj:`bool`): whether the server should be started by this process. False if run with an external
            WSGI. True is run by Flask.

    Returns:
        The application object needed by the WSGI server to run if ``auto_run`` is False, :obj:`None` otherwise.
    """

    setup_logging(logging_port)
    inspector = Inspector(int(min_to_self_delay))
    api = API(inspector, internal_api_endpoint)

    api.logger.info(f"Initialized. Serving at {endpoint}")

    if auto_run:
        wsgi_serve(api.app, listen=endpoint)
    else:
        return api.app


class API:
    """
    The :class:`API` is in charge of the interface between the user and the tower. It handles and serves user requests.
    The API is connected with the :class:`InternalAPI <teos.internal_api.InternalAPI>` via gRPC.

    Args:
        inspector (:obj:`Inspector <teos.inspector.Inspector>`): an :obj:`Inspector` instance to check the correctness
            of the received appointment data.
        internal_api_endpoint (:obj:`str`): the endpoint where the internal api is served.

    Attributes:
        logger (:obj:`Logger <teos.logger.Logger>`): The logger for this component.
        app: The Flask app of the API server.
        stub (:obj:`TowerServicesStub`): The rpc client stub.
    """

    def __init__(self, inspector, internal_api_endpoint):

        self.logger = get_logger(component=API.__name__)
        self.app = Flask(__name__)
        self.inspector = inspector
        self.internal_api_endpoint = internal_api_endpoint
        channel = grpc.insecure_channel(internal_api_endpoint)
        self.stub = TowerServicesStub(channel)

        # Adds all the routes to the functions listed above.
        routes = {
            "/register": (self.register, ["POST"]),
            "/add_appointment": (self.add_appointment, ["POST"]),
            "/get_appointment": (self.get_appointment, ["POST"]),
        }

        for url, params in routes.items():
            self.app.add_url_rule(url, view_func=params[0], methods=params[1])

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
            application error, and an error message. Error messages can be found at ``common.errors``.
        """

        remote_addr = get_remote_addr()
        self.logger.info("Received register request", from_addr="{}".format(remote_addr))

        # Check that data type and content are correct. Abort otherwise.
        try:
            request_data = get_request_data_json(request)

        except InvalidParameter as e:
            self.logger.info("Received invalid register request", from_addr="{}".format(remote_addr))
            return jsonify({"error": str(e), "error_code": errors.INVALID_REQUEST_FORMAT}), HTTP_BAD_REQUEST

        user_id = request_data.get("public_key")

        if user_id:
            try:
                r = self.stub.register(RegisterRequest(user_id=user_id))

                rcode = HTTP_OK
                response = json_format.MessageToDict(
                    r, including_default_value_fields=True, preserving_proto_field_name=True
                )
                response["public_key"] = user_id

            except grpc.RpcError as e:
                rcode = HTTP_BAD_REQUEST
                response = {"error": e.details(), "error_code": errors.REGISTRATION_MISSING_FIELD}

        else:
            rcode = HTTP_BAD_REQUEST
            response = {
                "error": "public_key not found in register message",
                "error_code": errors.REGISTRATION_WRONG_FIELD_FORMAT,
            }

        self.logger.info("Sending response and disconnecting", from_addr="{}".format(remote_addr), response=response)

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
            be found at ``common.errors``.
        """

        # Getting the real IP if the server is behind a reverse proxy
        remote_addr = get_remote_addr()
        self.logger.info("Received add_appointment request", from_addr="{}".format(remote_addr))

        # Check that data type and content are correct. Abort otherwise.
        try:
            request_data = get_request_data_json(request)

        except InvalidParameter as e:
            return jsonify({"error": str(e), "error_code": errors.INVALID_REQUEST_FORMAT}), HTTP_BAD_REQUEST

        try:
            appointment = self.inspector.inspect(request_data.get("appointment"))
            r = self.stub.add_appointment(
                AddAppointmentRequest(
                    appointment=Appointment(
                        locator=appointment.locator,
                        encrypted_blob=appointment.encrypted_blob,
                        to_self_delay=appointment.to_self_delay,
                    ),
                    signature=request_data.get("signature"),
                )
            )

            rcode = HTTP_OK
            response = json_format.MessageToDict(
                r, including_default_value_fields=True, preserving_proto_field_name=True
            )
        except InspectionFailed as e:
            rcode = HTTP_BAD_REQUEST
            response = {"error": "appointment rejected. {}".format(e.reason), "error_code": e.erno}

        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAUTHENTICATED:
                rcode = HTTP_BAD_REQUEST
                response = {
                    "error": f"appointment rejected. {e.details()}",
                    "error_code": errors.APPOINTMENT_INVALID_SIGNATURE_OR_SUBSCRIPTION_ERROR,
                }
            elif e.code() == grpc.StatusCode.ALREADY_EXISTS:
                rcode = HTTP_BAD_REQUEST
                response = {
                    "error": f"appointment rejected. {e.details()}",
                    "error_code": errors.APPOINTMENT_ALREADY_TRIGGERED,
                }
            else:
                # This covers grpc.StatusCode.RESOURCE_EXHAUSTED (and any other return).
                rcode = HTTP_SERVICE_UNAVAILABLE
                response = {"error": "appointment rejected"}

        self.logger.info("Sending response and disconnecting", from_addr="{}".format(remote_addr), response=response)
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

            - Appointments held by the :obj:`Watcher <teos.watcher.Watcher>` are flagged as
              ``AppointmentStatus.BEING_WATCHED``.
            - Appointments held by the :obj:`Responder <teos.responder.Responder>` are flagged as
              ``AppointmentStatus.DISPUTE_RESPONDED``.
            - Unknown appointments are flagged as ``AppointmentStatus.NOT_FOUND``.
        """

        # Getting the real IP if the server is behind a reverse proxy
        remote_addr = get_remote_addr()

        # Check that data type and content are correct. Abort otherwise.
        try:
            request_data = get_request_data_json(request)

        except InvalidParameter as e:
            self.logger.info("Received invalid get_appointment request", from_addr="{}".format(remote_addr))
            return jsonify({"error": str(e), "error_code": errors.INVALID_REQUEST_FORMAT}), HTTP_BAD_REQUEST

        locator = request_data.get("locator")

        try:
            self.inspector.check_locator(locator)
            self.logger.info("Received get_appointment request", from_addr="{}".format(remote_addr), locator=locator)

            r = self.stub.get_appointment(
                GetAppointmentRequest(locator=locator, signature=request_data.get("signature"))
            )
            data = (
                r.appointment_data.appointment
                if r.appointment_data.WhichOneof("appointment_data") == "appointment"
                else r.appointment_data.tracker
            )

            rcode = HTTP_OK
            response = {
                "locator": locator,
                "status": r.status,
                "appointment": json_format.MessageToDict(
                    data, including_default_value_fields=True, preserving_proto_field_name=True
                ),
            }

        except (InspectionFailed, grpc.RpcError) as e:
            if isinstance(e, grpc.RpcError) and e.code() == grpc.StatusCode.UNAUTHENTICATED:
                rcode = HTTP_BAD_REQUEST
                response = {
                    "error": e.details(),
                    "error_code": errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS,
                }
            else:
                rcode = HTTP_NOT_FOUND
                response = {"locator": locator, "status": AppointmentStatus.NOT_FOUND}

        return jsonify(response), rcode
