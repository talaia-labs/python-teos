import grpc
from concurrent import futures

from common.logger import get_logger
from common.appointment import Appointment
from common.exceptions import InvalidParameter

from teos.protobuf import user_pb2, api_pb2_grpc, appointment_pb2
from teos.gatekeeper import NotEnoughSlots, AuthenticationFailure
from teos.watcher import AppointmentLimitReached, AppointmentAlreadyTriggered, AppointmentNotFound


class API(api_pb2_grpc.APIServicer):
    def __init__(self, rw_lock, watcher):
        self.logger = get_logger(component=API.__name__)
        self.watcher = watcher

        # FIXME: Check if the lock should go or in the Watcher
        self.rw_lock = rw_lock

    def register(self, request, context):
        with self.rw_lock.gen_wlock():
            try:
                available_slots, subscription_expiry, subscription_signature = self.watcher.register(request.user_id)

                return user_pb2.RegisterResponse(
                    user_id=request.user_id,
                    available_slots=available_slots,
                    subscription_expiry=subscription_expiry,
                    signature=subscription_signature,
                )

            except InvalidParameter as e:
                context.set_details(e.msg)
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                return user_pb2.RegisterResponse()

    def add_appointment(self, request, context):
        with self.rw_lock.gen_wlock():
            try:
                appointment = Appointment(
                    request.appointment.locator, request.appointment.encrypted_blob, request.appointment.to_self_delay
                )
                return appointment_pb2.AddAppointmentResponse(
                    **self.watcher.add_appointment(appointment, request.signature)
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

            return appointment_pb2.AddAppointmentResponse()

    def get_appointment(self, request, context):
        with self.rw_lock.gen_wlock():
            try:
                data, status = self.watcher.get_appointment(request.locator, request.signature)
                if status == "being_watched":
                    data = appointment_pb2.AppointmentData(
                        appointment=appointment_pb2.Appointment(
                            locator=data.get("locator"),
                            encrypted_blob=data.get("encrypted_blob"),
                            to_self_delay=data.get("to_self_delay"),
                        )
                    )
                else:
                    data = appointment_pb2.AppointmentData(
                        tracker=appointment_pb2.Tracker(
                            locator=data.get("locator"),
                            dispute_txid=data.get("dispute_txid"),
                            penalty_txid=data.get("penalty_txid"),
                            penalty_rawtx=data.get("penalty_rawtx"),
                        )
                    )
                return appointment_pb2.GetAppointmentResponse(appointment_data=data, status=status)

            except (AuthenticationFailure, AppointmentNotFound):
                context.set_details("Appointment not found")
                context.set_code(grpc.StatusCode.NOT_FOUND)
                return appointment_pb2.GetAppointmentResponse()


# FIXME: This should inherit from another grpc file
class RPCServer:
    pass


def serve(rwlock, watcher):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    api_pb2_grpc.add_APIServicer_to_server(API(rwlock, watcher), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()
