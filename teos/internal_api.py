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
from teos.protobuf.user_pb2 import RegisterResponse
from teos.protobuf.api_pb2_grpc import HTTP_APIServicer, add_HTTP_APIServicer_to_server
from teos.protobuf.rpc_server_pb2_grpc import RPC_APIServicer, add_RPC_APIServicer_to_server
from teos.gatekeeper import NotEnoughSlots, AuthenticationFailure
from teos.watcher import AppointmentLimitReached, AppointmentAlreadyTriggered, AppointmentNotFound


class InternalAPI:
    def __init__(self, watcher):
        self.logger = get_logger(component=InternalAPI.__name__)
        self.watcher = watcher
        # lock to be acquired before interacting with the watchtower's state
        self.rw_lock = rwlock.RWLockWrite()


class InternalAPIHTTP(HTTP_APIServicer):
    def __init__(self, internal_api):
        self.internal_api = internal_api

    def register(self, request, context):
        with self.internal_api.rw_lock.gen_wlock():
            try:
                available_slots, subscription_expiry, subscription_signature = self.internal_api.watcher.register(
                    request.user_id
                )

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
        with self.internal_api.rw_lock.gen_wlock():
            try:
                appointment = Appointment(
                    request.appointment.locator, request.appointment.encrypted_blob, request.appointment.to_self_delay
                )
                return AddAppointmentResponse(
                    **self.internal_api.watcher.add_appointment(appointment, request.signature)
                )

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
        with self.internal_api.rw_lock.gen_rlock():
            try:
                data, status = self.internal_api.watcher.get_appointment(request.locator, request.signature)
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


class InternalAPIRPC(RPC_APIServicer):
    def __init__(self, internal_api):
        self.internal_api = internal_api

    def get_all_appointments(self, request, context):
        with self.internal_api.rw_lock.gen_rlock():
            watcher_appointments = self.internal_api.watcher.db_manager.load_watcher_appointments()
            responder_trackers = self.internal_api.watcher.db_manager.load_responder_trackers()

        appointments = Struct()
        appointments.update({"watcher_appointments": watcher_appointments, "responder_trackers": responder_trackers})

        return GetAllAppointmentsResponse(appointments=appointments)


def serve(watcher):
    # FIXME: Do we want to make this configurable? It should only be accesible from localhost
    endpoint = "localhost:50051"

    internal_api = InternalAPI(watcher)
    rpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_HTTP_APIServicer_to_server(InternalAPIHTTP(internal_api), rpc_server)
    add_RPC_APIServicer_to_server(InternalAPIRPC(internal_api), rpc_server)
    rpc_server.add_insecure_port(endpoint)
    rpc_server.start()

    internal_api.logger.info(f"Initialized. Serving at {endpoint}")
    rpc_server.wait_for_termination()
