import grpc
from concurrent import futures

from common.logger import get_logger
from common.exceptions import InvalidParameter

from teos.protobuf import user_pb2, api_pb2_grpc


class API(api_pb2_grpc.APIServicer):
    def __init__(self, rw_lock, inspector, watcher):
        self.logger = get_logger(component=API.__name__)
        self.inspector = inspector
        self.watcher = watcher
        # FIXME: Check if this should go here
        self.rw_lock = rw_lock

    def register(self, request, context):
        with self.rw_lock.gen_wlock():
            try:
                available_slots, subscription_expiry, subscription_signature = self.watcher.register(request.user_id)

            # FIXME: Add proper handling
            except InvalidParameter as e:
                self.logger(e)

        return user_pb2.Subscription(
            user=user_pb2.User(user_id=request.user_id),
            available_slots=available_slots,
            subscription_expiry=subscription_expiry,
            signature=subscription_signature,
        )

    def add_appointment(self, request, context):
        pass

    def get_appointment(self, request, context):
        pass


# FIXME: This should inherit from another grpc file
class RPCServer:
    pass


def serve(rwlock, inspector, watcher):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    api_pb2_grpc.add_APIServicer_to_server(API(rwlock, inspector, watcher), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    server.wait_for_termination()
