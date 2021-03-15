import json
import functools
import grpc

from google.protobuf import json_format
from google.protobuf.empty_pb2 import Empty

from common.cryptographer import Cryptographer
from common.tools import is_compressed_pk, intify
from common.exceptions import InvalidParameter

from teos.protobuf.tower_services_pb2_grpc import TowerServicesStub
from teos.protobuf.user_pb2 import GetUserRequest


def to_json(obj):
    """
    All conversions to json in this module should be consistent, therefore we restrict the options using
    this function.
    """
    return json.dumps(obj, indent=4)


def formatted(func):
    """
    Transforms the given function by wrapping the return value with ``json_format.MessageToDict`` followed by
    json.dumps, in order to print the result in a prettyfied json format.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        result_dict = json_format.MessageToDict(
            result, including_default_value_fields=True, preserving_proto_field_name=True
        )
        return to_json(intify(result_dict))

    return wrapper


class RPCClient:
    """
    Creates and keeps a connection to the an RPC serving TowerServices. It has methods to call each of the
    available grpc services, and it returns a pretty-printed json response.
    Errors from the grpc calls are not handled.

    Args:
        rpc_host (:obj:`str`): the IP or host where the RPC server is hosted.
        rpc_port (:obj:`int`): the port where the RPC server is hosted.
        rpc_cert_path (:obj:`str`): path to certificate used to validate the server's TSL credentials.
        rpc_user (:obj:`str`): a username that will be authenticated by the grpc server.
        rpc_pass (:obj:`str`): a password that will be authenticated by the grpc server.


    Attributes:
        stub: The rpc client stub.
    """

    def __init__(self, rpc_host, rpc_port, rpc_cert_path, rpc_user, rpc_pass):
        self.rpc_host = rpc_host
        self.rpc_port = rpc_port

        cert = Cryptographer.load_key_file(rpc_cert_path)
        user_creds = UserPassCallCredentials(rpc_user, rpc_pass)
        call_creds = grpc.metadata_call_credentials(user_creds)
        ssl_creds = grpc.ssl_channel_credentials(root_certificates=cert)
        creds = grpc.composite_channel_credentials(ssl_creds, call_creds)

        channel = grpc.secure_channel(f"{rpc_host}:{rpc_port}", creds)
        self.stub = TowerServicesStub(channel)

    @formatted
    def get_all_appointments(self):
        """Gets a list of all the appointments in the watcher, and trackers in the responder."""
        result = self.stub.get_all_appointments(Empty())
        return result.appointments

    @formatted
    def get_tower_info(self):
        """Gets generic information about the tower."""
        return self.stub.get_tower_info(Empty())

    def get_users(self):
        """Gets the list of registered user ids."""
        result = self.stub.get_users(Empty())
        return to_json(list(result.user_ids))

    @formatted
    def get_user(self, user_id):
        """
        Gets information about a specific user.

        Args:
            user_id (:obj:`str`): the id of the requested user.

        Raises:
            :obj:`InvalidParameter`: if `user_id` is not in the valid format.
        """

        if not is_compressed_pk(user_id):
            raise InvalidParameter("Invalid user id")

        result = self.stub.get_user(GetUserRequest(user_id=user_id))
        return result.user

    def stop(self):
        """Stops TEOS gracefully."""
        self.stub.stop(Empty())
        print("Closing the Eye of Satoshi")


class UserPassCallCredentials(grpc.AuthMetadataPlugin):
    """ 
    Creates call credentials, which include a username and password, to be passed to grpc.

    Args:
        username (:obj:`str`): a username that will be authenticated by the grpc server.
        password (:obj:`str`): a password that will be authenticated by the grpc server. 
    """
    def __init__(self, username, password):
        self._username = username
        self._password = password

    def __call__(self, context, callback): 
        metadata = [('user', self._username), ('pass', self._password)]
        callback(metadata, None)
