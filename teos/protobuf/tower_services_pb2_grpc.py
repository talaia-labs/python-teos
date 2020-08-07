# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

import teos.protobuf.appointment_pb2 as appointment__pb2
from google.protobuf import empty_pb2 as google_dot_protobuf_dot_empty__pb2
import teos.protobuf.user_pb2 as user__pb2


class TowerServicesStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.register = channel.unary_unary(
            "/teos.protobuf.protos.v1.TowerServices/register",
            request_serializer=user__pb2.RegisterRequest.SerializeToString,
            response_deserializer=user__pb2.RegisterResponse.FromString,
        )
        self.add_appointment = channel.unary_unary(
            "/teos.protobuf.protos.v1.TowerServices/add_appointment",
            request_serializer=appointment__pb2.AddAppointmentRequest.SerializeToString,
            response_deserializer=appointment__pb2.AddAppointmentResponse.FromString,
        )
        self.get_appointment = channel.unary_unary(
            "/teos.protobuf.protos.v1.TowerServices/get_appointment",
            request_serializer=appointment__pb2.GetAppointmentRequest.SerializeToString,
            response_deserializer=appointment__pb2.GetAppointmentResponse.FromString,
        )
        self.get_appointments = channel.unary_unary(
            "/teos.protobuf.protos.v1.TowerServices/get_appointments",
            request_serializer=appointment__pb2.GetAppointmentsRequest.SerializeToString,
            response_deserializer=appointment__pb2.GetAppointmentsResponse.FromString,
        )
        self.get_all_appointments = channel.unary_unary(
            "/teos.protobuf.protos.v1.TowerServices/get_all_appointments",
            request_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            response_deserializer=appointment__pb2.GetAllAppointmentsResponse.FromString,
        )
        self.get_tower_info = channel.unary_unary(
            "/teos.protobuf.protos.v1.TowerServices/get_tower_info",
            request_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            response_deserializer=appointment__pb2.GetTowerInfoResponse.FromString,
        )
        self.get_users = channel.unary_unary(
            "/teos.protobuf.protos.v1.TowerServices/get_users",
            request_serializer=google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            response_deserializer=user__pb2.GetUsersResponse.FromString,
        )
        self.get_user = channel.unary_unary(
            "/teos.protobuf.protos.v1.TowerServices/get_user",
            request_serializer=user__pb2.GetUserRequest.SerializeToString,
            response_deserializer=user__pb2.GetUserResponse.FromString,
        )


class TowerServicesServicer(object):
    """Missing associated documentation comment in .proto file."""

    def register(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def add_appointment(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def get_appointment(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def get_appointments(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def get_all_appointments(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def get_tower_info(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def get_users(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")

    def get_user(self, request, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("Method not implemented!")
        raise NotImplementedError("Method not implemented!")


def add_TowerServicesServicer_to_server(servicer, server):
    rpc_method_handlers = {
        "register": grpc.unary_unary_rpc_method_handler(
            servicer.register,
            request_deserializer=user__pb2.RegisterRequest.FromString,
            response_serializer=user__pb2.RegisterResponse.SerializeToString,
        ),
        "add_appointment": grpc.unary_unary_rpc_method_handler(
            servicer.add_appointment,
            request_deserializer=appointment__pb2.AddAppointmentRequest.FromString,
            response_serializer=appointment__pb2.AddAppointmentResponse.SerializeToString,
        ),
        "get_appointment": grpc.unary_unary_rpc_method_handler(
            servicer.get_appointment,
            request_deserializer=appointment__pb2.GetAppointmentRequest.FromString,
            response_serializer=appointment__pb2.GetAppointmentResponse.SerializeToString,
        ),
        "get_appointments": grpc.unary_unary_rpc_method_handler(
            servicer.get_appointments,
            request_deserializer=appointment__pb2.GetAppointmentsRequest.FromString,
            response_serializer=appointment__pb2.GetAppointmentsResponse.SerializeToString,
        ),
        "get_all_appointments": grpc.unary_unary_rpc_method_handler(
            servicer.get_all_appointments,
            request_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
            response_serializer=appointment__pb2.GetAllAppointmentsResponse.SerializeToString,
        ),
        "get_tower_info": grpc.unary_unary_rpc_method_handler(
            servicer.get_tower_info,
            request_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
            response_serializer=appointment__pb2.GetTowerInfoResponse.SerializeToString,
        ),
        "get_users": grpc.unary_unary_rpc_method_handler(
            servicer.get_users,
            request_deserializer=google_dot_protobuf_dot_empty__pb2.Empty.FromString,
            response_serializer=user__pb2.GetUsersResponse.SerializeToString,
        ),
        "get_user": grpc.unary_unary_rpc_method_handler(
            servicer.get_user,
            request_deserializer=user__pb2.GetUserRequest.FromString,
            response_serializer=user__pb2.GetUserResponse.SerializeToString,
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler("teos.protobuf.protos.v1.TowerServices", rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


# This class is part of an EXPERIMENTAL API.
class TowerServices(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def register(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/teos.protobuf.protos.v1.TowerServices/register",
            user__pb2.RegisterRequest.SerializeToString,
            user__pb2.RegisterResponse.FromString,
            options,
            channel_credentials,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def add_appointment(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/teos.protobuf.protos.v1.TowerServices/add_appointment",
            appointment__pb2.AddAppointmentRequest.SerializeToString,
            appointment__pb2.AddAppointmentResponse.FromString,
            options,
            channel_credentials,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def get_appointment(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/teos.protobuf.protos.v1.TowerServices/get_appointment",
            appointment__pb2.GetAppointmentRequest.SerializeToString,
            appointment__pb2.GetAppointmentResponse.FromString,
            options,
            channel_credentials,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def get_appointments(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/teos.protobuf.protos.v1.TowerServices/get_appointments",
            appointment__pb2.GetAppointmentsRequest.SerializeToString,
            appointment__pb2.GetAppointmentsResponse.FromString,
            options,
            channel_credentials,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def get_all_appointments(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/teos.protobuf.protos.v1.TowerServices/get_all_appointments",
            google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            appointment__pb2.GetAllAppointmentsResponse.FromString,
            options,
            channel_credentials,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def get_tower_info(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/teos.protobuf.protos.v1.TowerServices/get_tower_info",
            google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            appointment__pb2.GetTowerInfoResponse.FromString,
            options,
            channel_credentials,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def get_users(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/teos.protobuf.protos.v1.TowerServices/get_users",
            google_dot_protobuf_dot_empty__pb2.Empty.SerializeToString,
            user__pb2.GetUsersResponse.FromString,
            options,
            channel_credentials,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )

    @staticmethod
    def get_user(
        request,
        target,
        options=(),
        channel_credentials=None,
        call_credentials=None,
        compression=None,
        wait_for_ready=None,
        timeout=None,
        metadata=None,
    ):
        return grpc.experimental.unary_unary(
            request,
            target,
            "/teos.protobuf.protos.v1.TowerServices/get_user",
            user__pb2.GetUserRequest.SerializeToString,
            user__pb2.GetUserResponse.FromString,
            options,
            channel_credentials,
            call_credentials,
            compression,
            wait_for_ready,
            timeout,
            metadata,
        )
