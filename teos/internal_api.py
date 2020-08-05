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
from teos.protobuf.tower_services_pb2_grpc import TowerServicesServicer, add_TowerServicesServicer_to_server
from teos.gatekeeper import NotEnoughSlots, AuthenticationFailure
from teos.watcher import AppointmentLimitReached, AppointmentAlreadyTriggered, AppointmentNotFound


class InternalAPI:
    def __init__(self, watcher):
        self.logger = get_logger(component=InternalAPI.__name__)
        self.watcher = watcher
        self.rw_lock = rwlock.RWLockWrite()  # lock to be acquired before interacting with the watchtower's state
        self.endpoint = "localhost:50051"
        self.rpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        self.rpc_server.add_insecure_port(self.endpoint)
        add_TowerServicesServicer_to_server(_InternalAPI(self.rw_lock, watcher, self.logger), self.rpc_server)


class _InternalAPI(TowerServicesServicer):
    def __init__(self, rw_lock, watcher, logger):
        self.rw_lock = rw_lock
        self.watcher = watcher
        self.logger = logger

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
        with self.rw_lock.gen_rlock():
            watcher_appointments = self.watcher.db_manager.load_watcher_appointments()
            responder_trackers = self.watcher.db_manager.load_responder_trackers()

        appointments = Struct()
        appointments.update({"watcher_appointments": watcher_appointments, "responder_trackers": responder_trackers})

        return GetAllAppointmentsResponse(appointments=appointments)
