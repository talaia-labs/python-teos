import grpc
from concurrent import futures

from common.logger import get_logger

from teos.protobuf.rpc_server_pb2_grpc import RPC_APIStub, RPC_APIServicer, add_RPC_APIServicer_to_server


class RPC(RPC_APIServicer):
    def get_all_appointments(self, request, context):
        with grpc.insecure_channel("localhost:50051") as channel:
            stub = RPC_APIStub(channel)
            return stub.get_all_appointments(request)


def serve(rpc_bind, rpc_port):
    logger = get_logger(component=RPC.__name__)
    endpoint = f"{rpc_bind}:{rpc_port}"

    rpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_RPC_APIServicer_to_server(RPC(), rpc_server)
    rpc_server.add_insecure_port(endpoint)
    rpc_server.start()

    logger.info(f"Initialized. Serving at {endpoint}")
    rpc_server.wait_for_termination()
