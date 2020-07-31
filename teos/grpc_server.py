import grpc
from concurrent import futures
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
from teos.protobuf.api_pb2_grpc import APIServicer, add_APIServicer_to_server
from teos.protobuf.rpc_server_pb2_grpc import RPC_SERVERServicer, add_RPC_SERVERServicer_to_server
from teos.gatekeeper import NotEnoughSlots, AuthenticationFailure
from teos.watcher import AppointmentLimitReached, AppointmentAlreadyTriggered, AppointmentNotFound


class API(APIServicer):
    def __init__(self, rw_lock, watcher):
        self.logger = get_logger(component=API.__name__)
        self.watcher = watcher
        self.rw_lock = rw_lock
        self.logger.info("Initialized")

    def register(self, request, context):
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
        with self.rw_lock.gen_wlock():
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


# FIXME: This should inherit from another grpc file
class RPCServer(RPC_SERVERServicer):
    def __init__(self, rw_lock, watcher):
        self.logger = get_logger(component=RPCServer.__name__)
        self.watcher = watcher
        self.rw_lock = rw_lock
        self.logger.info("Initialized")

    def get_all_appointments(self, request, context):
        with self.rw_lock.gen_rlock():
            watcher_appointments = self.watcher.db_manager.load_watcher_appointments()
            responder_trackers = self.watcher.db_manager.load_responder_trackers()

        appointments = Struct()
        appointments.update({"watcher_appointments": watcher_appointments, "responder_trackers": responder_trackers})

        return GetAllAppointmentsResponse(appointments=appointments)


def serve(rwlock, watcher):
    api_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_APIServicer_to_server(API(rwlock, watcher), api_server)
    api_server.add_insecure_port("[::]:50051")
    api_server.start()

    rpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_RPC_SERVERServicer_to_server(RPCServer(rwlock, watcher), rpc_server)
    rpc_server.add_insecure_port("[::]:8814")
    rpc_server.start()

    api_server.wait_for_termination()
    rpc_server.wait_for_termination()
