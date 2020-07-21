#!/usr/bin/env python3

import os
import sys
import time
import json
import binascii
import requests
from sys import argv
from uuid import uuid4
from coincurve import PublicKey
from getopt import getopt, GetoptError
from requests import Timeout, ConnectionError
from requests.exceptions import MissingSchema, InvalidSchema, InvalidURL

from common import constants
from common.logger import get_logger, setup_logging
import common.receipts as receipts
from common.appointment import Appointment
from common.config_loader import ConfigLoader
from common.cryptographer import Cryptographer
from common.tools import setup_data_folder
from common.exceptions import InvalidKey, InvalidParameter, SignatureError
from common.tools import is_256b_hex_str, is_locator, compute_locator, is_compressed_pk

from .exceptions import TowerResponseError
from . import DEFAULT_CONF, DATA_DIR, CONF_FILE_NAME
from .help import show_usage, help_get_all_appointments

logger = get_logger()


def get_all_appointments(rpc_url):
    """
    Gets information about all appointments stored in the tower, if the user requesting the data is an administrator.

    Args:
        rpc_url (:obj:`str`): the url ofr the teos RPC.

    Returns:
        :obj:`dict` a dictionary containing all the appointments stored by the Responder and Watcher if the tower
        responds.
    """

    try:
        response = requests.post(
            url=rpc_url,
            json={
                "method": "get_all_appointments",
                "params": [],
                "jsonrpc": "2.0",
                "id": 0,  # TODO: handle ids correctly
            },
            timeout=5,
        )

        if response.status_code != constants.HTTP_OK:
            logger.error("The server returned an error", status_code=response.status_code, reason=response.reason)
            return None

        response_json = json.dumps(response.json(), indent=4, sort_keys=True)
        return response_json

    except ConnectionError:
        logger.error("Can't connect to the Eye of Satoshi. RPC server cannot be reached")
        return None

    except requests.exceptions.Timeout:
        logger.error("The request timed out")
        return None


def main(command, args, command_line_conf):
    # Loads config and sets up the data folder and log file
    config_loader = ConfigLoader(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF, command_line_conf)
    config = config_loader.build_config()

    setup_data_folder(DATA_DIR)
    setup_logging(config.get("LOG_FILE"))

    # Set the teos url
    teos_rpc_url = "{}:{}/rpc".format(config.get("RPC_CONNECT"), config.get("RPC_PORT"))
    # If an http or https prefix if found, leaves the server as is. Otherwise defaults to http.
    if not teos_rpc_url.startswith("http"):
        teos_rpc_url = "http://" + teos_rpc_url

    try:
        if command == "get_all_appointments":
            appointment_data = get_all_appointments(teos_rpc_url)
            if appointment_data:
                print(appointment_data)

        elif command == "help":
            if args:
                command = args.pop(0)

                if command == "get_all_appointments":
                    sys.exit(help_get_all_appointments())

                else:
                    logger.error("Unknown command. Use help to check the list of available commands")

            else:
                sys.exit(show_usage())

    except (FileNotFoundError, IOError, ConnectionError, ValueError) as e:
        logger.error(str(e))
    except (InvalidKey, InvalidParameter, TowerResponseError, SignatureError) as e:
        logger.error(e.msg, **e.kwargs)
    except Exception as e:
        logger.error("Unknown error occurred", error=str(e))


if __name__ == "__main__":
    command_line_conf = {}
    commands = ["get_all_appointments", "help"]

    try:
        opts, args = getopt(argv[1:], "h", ["rpcconnect=", "rpcport=", "help"])

        for opt, arg in opts:
            if opt in ["--rpcconnect"]:
                if arg:
                    command_line_conf["RPC_CONNECT"] = arg

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
