import grpc
from concurrent import futures

from common.logger import get_logger

from teos.protobuf.tower_services_pb2_grpc import (
    TowerServicesStub,
    TowerServicesServicer,
    add_TowerServicesServicer_to_server,
)


class RPC:
    def __init__(self, rpc_bind, rpc_port, internal_api_endpoint):
        self.logger = get_logger(component=RPC.__name__)
        self.endpoint = f"{rpc_bind}:{rpc_port}"
        self.rpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        self.rpc_server.add_insecure_port(self.endpoint)
        add_TowerServicesServicer_to_server(_RPC(internal_api_endpoint, self.logger), self.rpc_server)


class _RPC(TowerServicesServicer):
    def __init__(self, internal_api_endpoint, logger):
        self.logger = logger
        self.internal_api_endpoint = internal_api_endpoint

    def get_all_appointments(self, request, context):
        with grpc.insecure_channel(self.internal_api_endpoint) as channel:
            stub = TowerServicesStub(channel)
            return stub.get_all_appointments(request)


def serve(rpc_bind, rpc_port, internal_api_endpoint):
    rpc = RPC(rpc_bind, rpc_port, internal_api_endpoint)
    rpc.rpc_server.start()

    rpc.logger.info(f"Initialized. Serving at {rpc.endpoint}")
    rpc.rpc_server.wait_for_termination()
