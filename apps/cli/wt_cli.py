import os
import sys
import json
import requests
import time
import binascii
from sys import argv
from getopt import getopt, GetoptError
from requests import ConnectTimeout, ConnectionError
from uuid import uuid4

from apps.cli import config, LOG_PREFIX
from apps.cli.help import help_add_appointment, help_get_appointment
from common.blob import Blob

import common.cryptographer
from common import constants
from common.logger import Logger
from common.appointment import Appointment
from common.cryptographer import Cryptographer
from common.tools import check_sha256_hex_format, check_locator_format, compute_locator

logger = Logger(actor="Client", log_name_prefix=LOG_PREFIX)
common.cryptographer.logger = Logger(actor="Cryptographer", log_name_prefix=LOG_PREFIX)

# FIXME: creating a simpler load_keys for the alpha. Client keys will not be necessary. PISA key is hardcoded.
# def load_keys(pisa_pk_path, cli_sk_path, cli_pk_path):
#     """
#     Loads all the keys required so sign, send, and verify the appointment.
#
#     Args:
#         pisa_pk_path (:obj:`str`): path to the PISA public key file.
#         cli_sk_path (:obj:`str`): path to the client private key file.
#         cli_pk_path (:obj:`str`): path to the client public key file.
#
#     Returns:
#         :obj:`tuple` or ``None``: a three item tuple containing a pisa_pk object, cli_sk object and the cli_sk_der
#         encoded key if all keys can be loaded. ``None`` otherwise.
#     """
#
#     pisa_pk_der = Cryptographer.load_key_file(pisa_pk_path)
#     pisa_pk = Cryptographer.load_public_key_der(pisa_pk_der)
#
#     if pisa_pk is None:
#         logger.error("PISA's public key file not found. Please check your settings")
#         return None
#
#     cli_sk_der = Cryptographer.load_key_file(cli_sk_path)
#     cli_sk = Cryptographer.load_private_key_der(cli_sk_der)
#
#     if cli_sk is None:
#         logger.error("Client's private key file not found. Please check your settings")
#         return None
#
#     cli_pk_der = Cryptographer.load_key_file(cli_pk_path)
#
#     if cli_pk_der is None:
#         logger.error("Client's public key file not found. Please check your settings")
#         return None
#
#     return pisa_pk, cli_sk, cli_pk_der


def load_keys():
    PISA_PUBLIC_KEY = "3056301006072a8648ce3d020106052b8104000a0342000430053e39c53b8bcb43354a4ed886b8082af1d1e8fc14956e60ad0592bfdfab511b7e309f6ac83b7495462196692e145bf7b1a321e96ec8fc4d678719c77342da"
    pisa_pk = Cryptographer.load_public_key_der(binascii.unhexlify(PISA_PUBLIC_KEY))

    return pisa_pk


def add_appointment(args):
    """
    Manages the add_appointment command, from argument parsing, trough sending the appointment to the tower, until
    saving the appointment receipt.

    The life cycle of the function is as follows:
        - Load the add_appointment arguments
        - Check that the given commitment_txid is correct (proper format and not missing)
        - Check that the transaction is correct (not missing)
        - Create the appointment locator and encrypted blob from the commitment_txid and the penalty_tx
        - Load the client private key and sign the appointment
        - Send the appointment to the tower
        - Wait for the response
        - Check the tower's response and signature
        - Store the receipt (appointment + signature) on disk

    If any of the above-mentioned steps fails, the method returns false, otherwise it returns true.

    Args:
        args (:obj:`list`): a list of arguments to pass to ``parse_add_appointment_args``. Must contain a json encoded
            appointment, or the file option and the path to a file containing a json encoded appointment.

    Returns:
        :obj:`bool`: True if the appointment is accepted by the tower and the receipt is properly stored, false if any
        error occurs during the process.
    """
    # FIXME: creating a simpler load_keys for the alpha. Client keys will not be necessary. PISA key is hardcoded.
    # pisa_pk, cli_sk, cli_pk_der = load_keys(
    #     config.get("PISA_PUBLIC_KEY"), config.get("CLI_PRIVATE_KEY"), config.get("CLI_PUBLIC_KEY")
    # )
    #
    # try:
    #     hex_pk_der = binascii.hexlify(cli_pk_der)
    #
    # except binascii.Error as e:
    #     logger.error("Could not successfully encode public key as hex", error=str(e))
    #     return False
    pisa_pk = load_keys()

    if pisa_pk is None:
        return False

    # Get appointment data from user.
    appointment_data = parse_add_appointment_args(args)

    if appointment_data is None:
        logger.error("The provided appointment JSON is empty")
        return False

    valid_txid = check_sha256_hex_format(appointment_data.get("tx_id"))

    if not valid_txid:
        logger.error("The provided txid is not valid")
        return False

    tx_id = appointment_data.get("tx_id")
    tx = appointment_data.get("tx")

    if None not in [tx_id, tx]:
        appointment_data["locator"] = compute_locator(tx_id)
        appointment_data["encrypted_blob"] = Cryptographer.encrypt(Blob(tx), tx_id)

    else:
        logger.error("Appointment data is missing some fields")
        return False

    appointment = Appointment.from_dict(appointment_data)

    # FIXME: getting rid of the client-side signature for the alpha. A proper authentication is required.
    # signature = Cryptographer.sign(appointment.serialize(), cli_sk)
    #
    # if not (appointment and signature):
    #     return False
    #
    # data = {"appointment": appointment.to_dict(), "signature": signature, "public_key": hex_pk_der.decode("utf-8")}
    data = {"appointment": appointment.to_dict()}

    # Send appointment to the server.
    server_response = post_appointment(data)
    if server_response is None:
        return False

    response_json = process_post_appointment_response(server_response)

    if response_json is None:
        return False

    signature = response_json.get("signature")
    # Check that the server signed the appointment as it should.
    if signature is None:
        logger.error("The response does not contain the signature of the appointment")
        return False

    if not Cryptographer.verify(appointment.serialize(), signature, pisa_pk):
        logger.error("The returned appointment's signature is invalid")
        return False

    logger.info("Appointment accepted and signed by the Eye of Satoshi")

    # All good, store appointment and signature
    return save_appointment_receipt(appointment.to_dict(), signature)


def parse_add_appointment_args(args):
    """
    Parses the arguments of the add_appointment command.

    Args:
        args (:obj:`list`): a list of arguments to pass to ``parse_add_appointment_args``. Must contain a json encoded
            appointment, or the file option and the path to a file containing a json encoded appointment.

    Returns:
        :obj:`dict` or :obj:`None`: A dictionary containing the appointment data if it can be loaded. ``None``
        otherwise.
    """

    use_help = "Use 'help add_appointment' for help of how to use the command"

    if not args:
        logger.error("No appointment data provided. " + use_help)
        return None

    arg_opt = args.pop(0)

    try:
        if arg_opt in ["-h", "--help"]:
            sys.exit(help_add_appointment())

        if arg_opt in ["-f", "--file"]:
            fin = args.pop(0)
            if not os.path.isfile(fin):
                logger.error("Can't find file", filename=fin)
                return None

            try:
                with open(fin) as f:
                    appointment_data = json.load(f)

            except IOError as e:
                logger.error("I/O error", errno=e.errno, error=e.strerror)
                return None
        else:
            appointment_data = json.loads(arg_opt)

    except json.JSONDecodeError:
        logger.error("Non-JSON encoded data provided as appointment. " + use_help)
        return None

    return appointment_data


def post_appointment(data):
    """
    Sends appointment data to add_appointment endpoint to be processed by the tower.

    Args:
        data (:obj:`dict`): a dictionary containing three fields: an appointment, the client-side signature, and the
            der-encoded client public key.

    Returns:
        :obj:`dict` or ``None``: a json-encoded dictionary with the server response if the data can be posted.
        None otherwise.
    """

    logger.info("Sending appointment to the Eye of Satoshi")

    try:
        add_appointment_endpoint = "{}:{}".format(pisa_api_server, pisa_api_port)
        return requests.post(url=add_appointment_endpoint, json=json.dumps(data), timeout=5)

    except ConnectTimeout:
        logger.error("Can't connect to the Eye of Satoshi's API. Connection timeout")
        return None

    except ConnectionError:
        logger.error("Can't connect to the Eye of Satoshi's API. Server cannot be reached")
        return None

    except requests.exceptions.InvalidSchema:
        logger.error("No transport protocol found. Have you missed http(s):// in the server url?")

    except requests.exceptions.Timeout:
        logger.error("The request timed out")


def process_post_appointment_response(response):
    """
    Processes the server response to an add_appointment request.

    Args:
        response (:obj:`requests.models.Response`): a ``Response` object obtained from the sent request.

    Returns:
        :obj:`dict` or :obj:`None`: a dictionary containing the tower's response data if it can be properly parsed and
        the response type is ``HTTP_OK``. ``None`` otherwise.
    """

    try:
        response_json = response.json()

    except json.JSONDecodeError:
        logger.error(
            "The server returned a non-JSON response", status_code=response.status_code, reason=response.reason
        )
        return None

    if response.status_code != constants.HTTP_OK:
        if "error" not in response_json:
            logger.error(
                "The server returned an error status code but no error description", status_code=response.status_code
            )
        else:
            error = response_json["error"]
            logger.error(
                "The server returned an error status code with an error description",
                status_code=response.status_code,
                description=error,
            )
        return None

    return response_json


def save_appointment_receipt(appointment, signature):
    """
    Saves an appointment receipt to disk. A receipt consists in an appointment and a signature from the tower.

    Args:
        appointment (:obj:`Appointment <common.appointment.Appointment>`): the appointment to be saved on disk.
        signature (:obj:`str`): the signature of the appointment performed by the tower.

    Returns:
        :obj:`bool`: True if the appointment if properly saved, false otherwise.

    Raises:
        IOError: if an error occurs whilst writing the file on disk.
    """

    # Create the appointments directory if it doesn't already exist
    os.makedirs(config.get("APPOINTMENTS_FOLDER_NAME"), exist_ok=True)

    timestamp = int(time.time())
    locator = appointment["locator"]
    uuid = uuid4().hex  # prevent filename collisions

    filename = "{}/appointment-{}-{}-{}.json".format(config.get("APPOINTMENTS_FOLDER_NAME"), timestamp, locator, uuid)
    data = {"appointment": appointment, "signature": signature}

    try:
        with open(filename, "w") as f:
            json.dump(data, f)
            logger.info("Appointment saved at {}".format(filename))
            return True

    except IOError as e:
        logger.error("There was an error while saving the appointment", error=e)
        return False


def get_appointment(locator):
    """
    Gets information about an appointment from the tower.

    Args:
        locator (:obj:`str`): the appointment locator used to identify it.

    Returns:
        :obj:`dict` or :obj:`None`: a dictionary containing thew appointment data if the locator is valid and the tower
        responds. ``None`` otherwise.
    """

    valid_locator = check_locator_format(locator)

    if not valid_locator:
        logger.error("The provided locator is not valid", locator=locator)
        return None

    get_appointment_endpoint = "{}:{}/get_appointment".format(pisa_api_server, pisa_api_port)
    parameters = "?locator={}".format(locator)

    try:
        r = requests.get(url=get_appointment_endpoint + parameters, timeout=5)
        return r.json()

    except ConnectTimeout:
        logger.error("Can't connect to the Eye of Satoshi's API. Connection timeout")
        return None

    except ConnectionError:
        logger.error("Can't connect to the Eye of Satoshi's API. Server cannot be reached")
        return None

    except requests.exceptions.InvalidSchema:
        logger.error("No transport protocol found. Have you missed http(s):// in the server url?")

    except requests.exceptions.Timeout:
        logger.error("The request timed out")


def show_usage():
    return (
        "USAGE: "
        "\n\tpython wt_cli.py [global options] command [command options] [arguments]"
        "\n\nCOMMANDS:"
        "\n\tadd_appointment \tRegisters a json formatted appointment with the tower."
        "\n\tget_appointment \tGets json formatted data about an appointment from the tower."
        "\n\thelp \t\t\tShows a list of commands or help for a specific command."
        "\n\nGLOBAL OPTIONS:"
        "\n\t-s, --server \tAPI server where to send the requests. Defaults to https://teos.pisa.watch (modifiable in "
        "config.py)"
        "\n\t-p, --port \tAPI port where to send the requests. Defaults to 443 (modifiable in conf.py)"
        "\n\t-d, --debug \tshows debug information and stores it in wt_cli.log"
        "\n\t-h --help \tshows this message."
    )


if __name__ == "__main__":
    pisa_api_server = config.get("DEFAULT_PISA_API_SERVER")
    pisa_api_port = config.get("DEFAULT_PISA_API_PORT")
    commands = ["add_appointment", "get_appointment", "help"]

    try:
        opts, args = getopt(argv[1:], "s:p:h", ["server", "port", "help"])

        for opt, arg in opts:
            if opt in ["-s", "server"]:
                if arg:
                    pisa_api_server = arg

            if opt in ["-p", "--port"]:
                if arg:
                    pisa_api_port = int(arg)

            if opt in ["-h", "--help"]:
                sys.exit(show_usage())

        if args:
            command = args.pop(0)

            if command in commands:
                if command == "add_appointment":
                    add_appointment(args)

                elif command == "get_appointment":
                    if not args:
                        logger.error("No arguments were given")

                    else:
                        arg_opt = args.pop(0)

                        if arg_opt in ["-h", "--help"]:
                            sys.exit(help_get_appointment())

                        appointment_data = get_appointment(arg_opt)
                        if appointment_data:
                            print(appointment_data)

                elif command == "help":
                    if args:
                        command = args.pop(0)

                        if command == "add_appointment":
                            sys.exit(help_add_appointment())

                        elif command == "get_appointment":
                            sys.exit(help_get_appointment())

                        else:
                            logger.error("Unknown command. Use help to check the list of available commands")

                    else:
                        sys.exit(show_usage())

            else:
                logger.error("Unknown command. Use help to check the list of available commands")

        else:
            logger.error("No command provided. Use help to check the list of available commands")

    except GetoptError as e:
        logger.error("{}".format(e))

    except json.JSONDecodeError as e:
        logger.error("Non-JSON encoded appointment passed as parameter")
