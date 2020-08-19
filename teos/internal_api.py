import grpc
from concurrent import futures
from readerwriterlock import rwlock
from google.protobuf.struct_pb2 import Struct

from common.logger import get_logger
from common.appointment import Appointment
from common.exceptions import InvalidParameter

from teos.protobuf.appointment_pb2 import (
    Appointment as AppointmentProto,
    Tracker as TrackerProto,
    AppointmentData,
    AddAppointmentResponse,
    GetAppointmentResponse,
    GetAllAppointmentsResponse,
)
from teos.protobuf.user_pb2 import RegisterResponse, GetUserResponse, GetUsersResponse
from teos.protobuf.tower_services_pb2 import GetTowerInfoResponse
from teos.protobuf.tower_services_pb2_grpc import TowerServicesServicer, add_TowerServicesServicer_to_server
from teos.gatekeeper import NotEnoughSlots, AuthenticationFailure
from teos.watcher import AppointmentLimitReached, AppointmentAlreadyTriggered, AppointmentNotFound
from google.protobuf.empty_pb2 import Empty


class InternalAPI:
    """
    The internal API is the interface to interact with the tower backend. It offers methods than can be accessed by the
    CLI or the client via the :class:`API <teos.api.API>` (HTTP proxy) or the :class:`RPC <teos.rpc.RPC>` (gRPC proxy).

    Args:
        watcher (:obj:`Watcher <teos.watcher.Watcher>`): a ``Watcher`` instance to pass the requests to. The Watcher is
            the main backend class of the tower and can interact with the rest.
        internal_api_endpoint (:obj:`str`): the endpoint where the internal api will be served (gRPC server).
        stop_command_event (:obj:`multiprocessing.Event`): an Event to be set when a `stop` command is issued.

    Attributes:
        logger (:obj:`Logger <common.logger.Logger>`): the logger for this component.
        endpoint (:obj:`str`): the endpoint where the internal api will be served (gRPC server).
        rpc_server (:obj:`Server <grpc.Server>`): the non-started gRPC server instance.
    """

    def __init__(self, watcher, internal_api_endpoint, stop_command_event):
        self.logger = get_logger(component=InternalAPI.__name__)
        self.watcher = watcher
        self.endpoint = internal_api_endpoint
        self.rpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        self.rpc_server.add_insecure_port(self.endpoint)
        add_TowerServicesServicer_to_server(_InternalAPI(watcher, stop_command_event, self.logger), self.rpc_server)


class _InternalAPI(TowerServicesServicer):
    """
    This represents the internal api service provider and implements all the gRPC methods offered by the API.

    Args:
        watcher (:obj:`Watcher <teos.watcher.Watcher>`): a ``Watcher`` instance to pass the requests to. The Watcher is
            the main backend class of the tower and can interact with the rest.
        stop_command_event (:obj:`multiprocessing.Event`): an Event to be set when a `stop` command is issued.
        logger (:obj:`Logger <common.logger.Logger>`): the logger for this component.

    Attributes:
        rw_lock (:obj:`RWLockWrite <rwlock.RWLockWrite>`): a reader-writer lock to manage concurrent access to the
            backend.
    """

    def __init__(self, watcher, stop_command_event, logger):
        self.watcher = watcher
        self.stop_command_event = stop_command_event
        self.logger = logger
        self.rw_lock = rwlock.RWLockWrite()  # lock to be acquired before interacting with the watchtower's state

    def register(self, request, context):
        """Registers a user to the tower."""
        with self.rw_lock.gen_wlock():
            try:
                available_slots, subscription_expiry, subscription_signature = self.watcher.register(request.user_id)

                return RegisterResponse(
                    user_id=request.user_id,
                    available_slots=available_slots,
                    subscription_expiry=subscription_expiry,
                    subscription_signature=subscription_signature,
                )

            except InvalidParameter as e:
                context.set_details(e.msg)
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                return RegisterResponse()

    def add_appointment(self, request, context):
        """Processes the request to add an appointment from a user."""
        with self.rw_lock.gen_wlock():
            try:
                appointment = Appointment(
                    request.appointment.locator, request.appointment.encrypted_blob, request.appointment.to_self_delay
                )
                return AddAppointmentResponse(**self.watcher.add_appointment(appointment, request.signature))

            except (AuthenticationFailure, NotEnoughSlots):
                msg = "Invalid signature or user does not have enough slots available"
                status_code = grpc.StatusCode.UNAUTHENTICATED

            except AppointmentLimitReached:
                msg = "Appointment limit reached"
                status_code = grpc.StatusCode.RESOURCE_EXHAUSTED

            except AppointmentAlreadyTriggered:
                msg = "The provided appointment has already been triggered"
                status_code = grpc.StatusCode.ALREADY_EXISTS

            context.set_details(msg)
            context.set_code(status_code)

            return AddAppointmentResponse()

    def get_appointment(self, request, context):
        """Returns an appointment stored in the tower, if it exists."""
        with self.rw_lock.gen_rlock():
            try:
                data, status = self.watcher.get_appointment(request.locator, request.signature)
                if status == "being_watched":
                    data = AppointmentData(
                        appointment=AppointmentProto(
                            locator=data.get("locator"),
                            encrypted_blob=data.get("encrypted_blob"),
                            to_self_delay=data.get("to_self_delay"),
                        )
                    )
                else:
                    data = AppointmentData(
                        tracker=TrackerProto(
                            locator=data.get("locator"),
                            dispute_txid=data.get("dispute_txid"),
                            penalty_txid=data.get("penalty_txid"),
                            penalty_rawtx=data.get("penalty_rawtx"),
                        )
                    )
                return GetAppointmentResponse(appointment_data=data, status=status)

            except (AuthenticationFailure, AppointmentNotFound):
                context.set_details("Appointment not found")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                return GetAppointmentResponse()

    def get_all_appointments(self, request, context):
        """Returns all the appointments in the tower."""
        with self.rw_lock.gen_rlock():
            watcher_appointments = self.watcher.get_all_watcher_appointments()
            responder_trackers = self.watcher.get_all_responder_trackers()

        appointments = Struct()
        appointments.update({"watcher_appointments": watcher_appointments, "responder_trackers": responder_trackers})

        return GetAllAppointmentsResponse(appointments=appointments)

    def get_tower_info(self, request, context):
        """Returns generic information about the tower."""
        with self.rw_lock.gen_rlock():
            return GetTowerInfoResponse(
                tower_id=self.watcher.tower_id,
                n_registered_users=self.watcher.n_registered_users,
                n_watcher_appointments=self.watcher.n_watcher_appointments,
                n_responder_trackers=self.watcher.n_responder_trackers,
            )

    def get_users(self, request, context):
        """Returns the list of all registered user ids."""
        with self.rw_lock.gen_rlock():
            return GetUsersResponse(user_ids=self.watcher.get_registered_user_ids())

    def get_user(self, request, context):
        """Returns information about a user, given its user id."""
        with self.rw_lock.gen_rlock():
            user_info = self.watcher.get_user_info(request.user_id)

            if not user_info:
                context.set_details("User not found")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                return GetUserResponse()

            user_struct = Struct()
            user_struct.update(
                {
                    "subscription_expiry": user_info.subscription_expiry,
                    "available_slots": user_info.available_slots,
                    "appointments": list(user_info.appointments.keys()),
                }
            )
            return GetUserResponse(user=user_struct)

    def stop(self, request, context):
        self.stop_command_event.set()
        return Empty()
