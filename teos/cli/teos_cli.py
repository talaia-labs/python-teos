#!/usr/bin/env python3

import sys
import json
import grpc
from sys import argv
import functools
from getopt import getopt, GetoptError
from requests import ConnectionError
from google.protobuf import json_format
from google.protobuf.empty_pb2 import Empty

from common.config_loader import ConfigLoader
from common.tools import setup_data_folder
from common.exceptions import InvalidKey, InvalidParameter, SignatureError, TowerResponseError

from teos import DEFAULT_CONF, DATA_DIR, CONF_FILE_NAME
from teos.cli.help import (
    show_usage,
    help_get_all_appointments,
    help_get_tower_info,
    help_get_users,
    help_get_user,
)
from teos.protobuf.tower_services_pb2_grpc import TowerServicesStub
from teos.protobuf.user_pb2 import GetUserRequest


def formatted(func):
    """Transforms the given function by wrapping the return value with json_format.MessageToDict followed by
    json.dumps, in order to print the result in a prettyfied json format.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        result_dict = json_format.MessageToDict(
            result, including_default_value_fields=True, preserving_proto_field_name=True
        )
        return json.dumps(result_dict, indent=4)

    return wrapper


class RPCClient:
    """Creates and keeps a connection to the an RPC serving TowerServices. It has methods to call each of the
    available grpc services, and it returns a pretty-printed json response.
    Errors from the grpc calls are not handled.
    """

    def __init__(self, rpc_host, rpc_port):
        self.rpc_host = rpc_host
        self.rpc_port = rpc_port
        self.channel = grpc.insecure_channel(f"{rpc_host}:{rpc_port}")
        self.stub = TowerServicesStub(self.channel)

    @formatted
    def get_all_appointments(self):
        return self.stub.get_all_appointments(Empty())

    @formatted
    def get_tower_info(self):
        return self.stub.get_tower_info(Empty())

    @formatted
    def get_users(self):
        return self.stub.get_users(Empty())

    @formatted
    def get_user(self, user_id):
        return self.stub.get_user(GetUserRequest(user_id=user_id))


def main(command, args, command_line_conf):
    # Loads config and sets up the data folder and log file
    config_loader = ConfigLoader(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF, command_line_conf)
    config = config_loader.build_config()

    setup_data_folder(DATA_DIR)

    teos_rpc_host = config.get("RPC_BIND")
    teos_rpc_port = config.get("RPC_PORT")

    rpc_client = RPCClient(teos_rpc_host, teos_rpc_port)

    try:
        if command == "get_all_appointments":
            result = rpc_client.get_all_appointments()

        elif command == "get_tower_info":
            result = rpc_client.get_tower_info()

        elif command == "get_users":
            result = rpc_client.get_users()

        elif command == "get_user":
            if not args:
                sys.exit("No user_id was given")
            if len(args) > 1:
                sys.exit(f"Expected only one argument, not {len(args)}")

            result = rpc_client.get_user(args[0])
        elif command == "help":
            if args:
                command = args.pop(0)

                if command == "get_all_appointments":
                    sys.exit(help_get_all_appointments())

                elif command == "get_tower_info":
                    sys.exit(help_get_tower_info())

                elif command == "get_users":
                    sys.exit(help_get_users())

                elif command == "get_user":
                    sys.exit(help_get_user())

                else:
                    sys.exit("Unknown command. Use help to check the list of available commands")

            else:
                sys.exit(show_usage())

    except grpc.RpcError as e:
        sys.exit(e.details())
    except (FileNotFoundError, IOError, ConnectionError, ValueError) as e:
        sys.exit(str(e))
    except (InvalidKey, InvalidParameter, TowerResponseError, SignatureError) as e:
        sys.exit(f"{e.msg}. Error arguments: {e.kwargs}")
    except Exception as e:
        sys.exit(f"Unknown error occurred: {str(e)}")

    if result:
        print(result)


if __name__ == "__main__":
    command_line_conf = {}
    commands = ["get_all_appointments", "get_appointments", "get_tower_info", "get_users", "get_user", "help"]

    try:
        opts, args = getopt(argv[1:], "h", ["rpcbind=", "rpcport=", "help"])

        for opt, arg in opts:
            if opt in ["--rpcbind"]:
                if arg:
                    command_line_conf["RPC_BIND"] = arg

            if opt in ["--rpcport"]:
                if arg:
                    try:
                        command_line_conf["RPC_PORT"] = int(arg)
                    except ValueError:
                        sys.exit("port must be an integer")

            if opt in ["-h", "--help"]:
                sys.exit(show_usage())

        command = args.pop(0) if args else None
        if command in commands:
            main(command, args, command_line_conf)
        elif not command:
            sys.exit("No command provided. Use help to check the list of available commands")
        else:
            sys.exit("Unknown command. Use help to check the list of available commands")

    except GetoptError as e:
        sys.exit("{}".format(e))
