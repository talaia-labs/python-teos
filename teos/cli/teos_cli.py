#!/usr/bin/env python3

import sys
import json
import grpc
from sys import argv
from getopt import getopt, GetoptError
from requests import ConnectionError
from google.protobuf import json_format
from google.protobuf.empty_pb2 import Empty

from common.config_loader import ConfigLoader
from common.tools import setup_data_folder
from common.exceptions import InvalidKey, InvalidParameter, SignatureError, TowerResponseError

from teos import DEFAULT_CONF, DATA_DIR, CONF_FILE_NAME
from teos.cli.help import show_usage, help_get_all_appointments
from teos.protobuf.tower_services_pb2_grpc import TowerServicesStub


def get_all_appointments(rpc_host, rpc_port):
    """
    Gets information about all appointments stored in the tower.

    Args:
        rpc_host (:obj:`str`): the hostname (or IP) where the rpc server is running.
        rpc_port (:obj:`int`): the port where the rpc server is running.

    Returns:
        :obj:`dict` a dictionary containing all the appointments stored by the Responder and Watcher if the tower
        responds.
    """

    try:
        with grpc.insecure_channel(f"{rpc_host}:{rpc_port}") as channel:
            stub = TowerServicesStub(channel)
            r = stub.get_all_appointments(Empty())
            response = json_format.MessageToDict(
                r.appointments, including_default_value_fields=True, preserving_proto_field_name=True
            )

        return response

    # FIXME: Handle different errors
    except grpc.RpcError:
        print("Can't connect to the Eye of Satoshi. RPC server cannot be reached", file=sys.stderr)
        return None


def main(command, args, command_line_conf):
    # Loads config and sets up the data folder and log file
    config_loader = ConfigLoader(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF, command_line_conf)
    config = config_loader.build_config()

    setup_data_folder(DATA_DIR)

    try:
        if command == "get_all_appointments":
            appointment_data = get_all_appointments(config.get("RPC_BIND"), config.get("RPC_PORT"))
            if appointment_data:
                print(json.dumps(appointment_data, indent=4, sort_keys=True))

        elif command == "help":
            if args:
                command = args.pop(0)

                if command == "get_all_appointments":
                    sys.exit(help_get_all_appointments())

                else:
                    sys.exit("Unknown command. Use help to check the list of available commands")

            else:
                sys.exit(show_usage())

    except (FileNotFoundError, IOError, ConnectionError, ValueError) as e:
        sys.exit(str(e))
    except (InvalidKey, InvalidParameter, TowerResponseError, SignatureError) as e:
        sys.exit(f"{e.msg}. Error arguments: {e.kwargs}")
    except Exception as e:
        sys.exit(f"Unknown error occurred: {str(e)}")


if __name__ == "__main__":
    command_line_conf = {}
    commands = ["get_all_appointments", "help"]

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
