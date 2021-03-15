import grpc
import functools
from concurrent import futures
from signal import signal, SIGINT

from teos.tools import ignore_signal
from teos.logger import setup_logging, get_logger
from teos.constants import SHUTDOWN_GRACE_TIME
from teos.protobuf.tower_services_pb2_grpc import (
    TowerServicesStub,
    TowerServicesServicer,
    add_TowerServicesServicer_to_server,
)


class AuthInterceptor(grpc.ServerInterceptor):
    """
    The :obj:`AuthInterceptor` looks at every call made to the RPC server to see if the correct CLI credentials are provided.

    Args:
        rpc_user (:obj:`str`): the username supplied by the CLI when calling the RPC server.
        rpc_pass (:obj:`str`): the password supplied by the CLI when calling the RPC server. 
        
    Attributes:
        rpc_user (:obj:`str`): the username supplied by the CLI when calling the RPC server.
        rpc_pass (:obj:`str`): the password supplied by the CLI when calling the RPC server. 
    """
    def __init__(self, rpc_user, rpc_pass):
        self.rpc_user = rpc_user
        self.rpc_pass = rpc_pass

        def abort(ignored_request, context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, 'Invalid user credentials')

        self._abortion = grpc.unary_unary_rpc_method_handler(abort)

    def intercept_service(self, continuation, handler_call_details):
        metadata = dict(handler_call_details.invocation_metadata)
        user = metadata.get("user")
        password = metadata.get("pass")

        if (user == self.rpc_user) and (password == self.rpc_pass):
            return continuation(handler_call_details)
        else:
            return self._abortion 


class RPC:
    """
    The :obj:`RPC` is an external RPC server offered by tower to receive requests from the CLI.
    This acts as a proxy between the internal api and the CLI.

    Args:
        rpc_bind (:obj:`str`): the IP or host where the RPC server will be hosted.
        rpc_port (:obj:`int`): the port where the RPC server will be hosted.
        internal_api_endpoint (:obj:`str`): the endpoint where to reach the internal (gRPC) api.

    Attributes:
        logger (:obj:`Logger <teos.logger.Logger>`): The logger for this component.
        endpoint (:obj:`str`): The endpoint where the RPC api will be served (external gRPC server).
        rpc_server (:obj:`grpc.Server <grpc.Server>`): The non-started gRPC server instance.
    """

    def __init__(self, rpc_bind, rpc_port, internal_api_endpoint, teos_sk, certificate, rpc_user, rpc_pass):
        self.logger = get_logger(component=RPC.__name__)
        self.endpoint = f"{rpc_bind}:{rpc_port}"

        an_interceptor = AuthInterceptor(rpc_user, rpc_pass)
        self.rpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), interceptors=[an_interceptor])
        server_credentials = grpc.ssl_server_credentials(((teos_sk, certificate,),))

        self.rpc_server.add_secure_port(self.endpoint, server_credentials)
        add_TowerServicesServicer_to_server(_RPC(internal_api_endpoint, self.logger, rpc_user, rpc_pass), self.rpc_server)

    def teardown(self):
        self.logger.info("Stopping")
        stopped_event = self.rpc_server.stop(SHUTDOWN_GRACE_TIME)
        stopped_event.wait()
        self.logger.info("Stopped")


def forward_errors(func):
    """
    Transforms ``func`` in order to forward any ``grpc.RPCError`` returned by the upstream grpc as the result of the
    current grpc call.
    """

    @functools.wraps(func)
    def wrapper(self, request, context, *args, **kwargs):
        try:
            return func(self, request, context, *args, **kwargs)
        except grpc.RpcError as e:
            context.set_details(e.details())
            context.set_code(e.code())

    return wrapper


class _RPC(TowerServicesServicer):
    """
    This represents the RPC server provider and implements all the methods that can be accessed using the CLI.

    Args:
        internal_api_endpoint (:obj:`str`): the endpoint where to reach the internal (gRPC) api.
        logger (:obj:`Logger <teos.logger.Logger>`): the logger for this component.

    Attributes:
        stub (:obj:`TowerServicesStub`): The rpc client stub.
    """

    def __init__(self, internal_api_endpoint, logger, rpc_user, rpc_pass):
        self.logger = logger
        self.internal_api_endpoint = internal_api_endpoint
        self.rpc_user = rpc_user
        self.rpc_pass = rpc_pass

        channel = grpc.insecure_channel(self.internal_api_endpoint)
        self.stub = TowerServicesStub(channel)

    @forward_errors
    def get_all_appointments(self, request, context):
        return self.stub.get_all_appointments(request)

    @forward_errors
    def get_tower_info(self, request, context):
        return self.stub.get_tower_info(request)

    @forward_errors
    def get_users(self, request, context):
        return self.stub.get_users(request)

    @forward_errors
    def get_user(self, request, context):
        return self.stub.get_user(request)

    @forward_errors
    def stop(self, request, context):
        return self.stub.stop(request)


def serve(rpc_bind, rpc_port, internal_api_endpoint, logging_port, stop_event, teos_key, rpc_cert, rpc_user, rpc_pass):
    """
    Serves the external RPC API at the given endpoint and connects it to the internal api.

    This method will serve and hold until the main process is stop or a stop signal is received.

    Args:
        rpc_bind (:obj:`str`): the IP or host where the RPC server will be hosted.
        rpc_port (:obj:`int`): the port where the RPC server will be hosted.
        internal_api_endpoint (:obj:`str`): the endpoint where to reach the internal (gRPC) api.
        logging_port (:obj:`int`): the port where the logging server can be reached (localhost:logging_port)
        stop_event (:obj:`multiprocessing.Event`) the Event that this service will monitor. The rpc server will
            initiate a graceful shutdown once this event is set.
    """

    setup_logging(logging_port)
    rpc = RPC(rpc_bind, rpc_port, internal_api_endpoint, teos_key, rpc_cert, rpc_user, rpc_pass)
    # Ignores SIGINT so the main process can handle the teardown
    signal(SIGINT, ignore_signal)
    rpc.rpc_server.start()

    rpc.logger.info(f"Initialized. Serving at {rpc.endpoint}")

    stop_event.wait()

    rpc.logger.info("Stopping")
    stopped_event = rpc.rpc_server.stop(SHUTDOWN_GRACE_TIME)
    stopped_event.wait()
    rpc.logger.info("Stopped")
