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
from apps.cli.blob import Blob

from common.logger import Logger
from common.appointment import Appointment
from common.cryptographer import Cryptographer
from common.tools import check_sha256_hex_format, check_locator_format, compute_locator


HTTP_OK = 200
logger = Logger(actor="Client", log_name_prefix=LOG_PREFIX)


# FIXME: TESTING ENDPOINT, WON'T BE THERE IN PRODUCTION
def generate_dummy_appointment():
    get_block_count_end_point = "http://{}:{}/get_block_count".format(pisa_api_server, pisa_api_port)
    r = requests.get(url=get_block_count_end_point, timeout=5)

    current_height = r.json().get("block_count")

    dummy_appointment_data = {
        "tx": os.urandom(192).hex(),
        "tx_id": os.urandom(32).hex(),
        "start_time": current_height + 5,
        "end_time": current_height + 10,
        "to_self_delay": 20,
    }

    logger.info(
        "Generating dummy appointment data:" "\n\n" + json.dumps(dummy_appointment_data, indent=4, sort_keys=True)
    )

    json.dump(dummy_appointment_data, open("dummy_appointment_data.json", "w"))

    logger.info("\nData stored in dummy_appointment_data.json")


# Loads and returns Pisa keys from disk
def load_key_file_data(file_name):
    try:
        with open(file_name, "rb") as key_file:
            key = key_file.read()
        return key

    except FileNotFoundError as e:
        logger.error("Client's key file not found. Please check your settings")
        raise e

    except IOError as e:
        logger.error("I/O error({}): {}".format(e.errno, e.strerror))
        raise e


# Makes sure that the folder APPOINTMENTS_FOLDER_NAME exists, then saves the appointment and signature in it.
def save_signed_appointment(appointment, signature):
    # Create the appointments directory if it doesn't already exist
    os.makedirs(config.get("APPOINTMENTS_FOLDER_NAME"), exist_ok=True)

    timestamp = int(time.time())
    locator = appointment["locator"]
    uuid = uuid4().hex  # prevent filename collisions

    filename = "{}/appointment-{}-{}-{}.json".format(config.get("APPOINTMENTS_FOLDER_NAME"), timestamp, locator, uuid)
    data = {"appointment": appointment, "signature": signature}

    with open(filename, "w") as f:
        json.dump(data, f)


def add_appointment(args):
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

    signature = get_appointment_signature(appointment)
    hex_pk_der = get_pk()

    if not (appointment and signature and hex_pk_der):
        return False

    data = {"appointment": appointment.to_dict(), "signature": signature, "public_key": hex_pk_der.decode("utf-8")}

    # Send appointment to the server.
    response_json = post_data_to_add_appointment_endpoint(data)

    if response_json is None:
        return False

    signature = response_json.get("signature")
    # Check that the server signed the appointment as it should.
    if signature is None:
        logger.error("The response does not contain the signature of the appointment")
        return False

    valid = check_signature(signature, appointment)

    if not valid:
        logger.error("The returned appointment's signature is invalid")
        return False

    logger.info("Appointment accepted and signed by Pisa")
    # all good, store appointment and signature
    try:
        save_signed_appointment(appointment.to_dict(), signature)

    except OSError as e:
        logger.error("There was an error while saving the appointment", error=e)
        return False

    return True


# Parse arguments passed to add_appointment and handle them accordingly.
# Returns appointment data.
def parse_add_appointment_args(args):
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


# Sends appointment data to add_appointment endpoint to be processed by the server.
def post_data_to_add_appointment_endpoint(data):
    logger.info("Sending appointment to PISA")

    try:
        add_appointment_endpoint = "http://{}:{}".format(pisa_api_server, pisa_api_port)
        r = requests.post(url=add_appointment_endpoint, json=json.dumps(data), timeout=5)

        response_json = r.json()

    except json.JSONDecodeError:
        logger.error("The response was not valid JSON")
        return None

    except ConnectTimeout:
        logger.error("Can't connect to pisa API. Connection timeout")
        return None

    except ConnectionError:
        logger.error("Can't connect to pisa API. Server cannot be reached")
        return None

    if r.status_code != HTTP_OK:
        if "error" not in response_json:
            logger.error("The server returned an error status code but no error description", status_code=r.status_code)
        else:
            error = response_json["error"]
            logger.error(
                "The server returned an error status code with an error description",
                status_code=r.status_code,
                description=error,
            )
        return None

    if "signature" not in response_json:
        logger.error("The response does not contain the signature of the appointment")
        return None

    return response_json


# Verify that the signature returned from the watchtower is valid.
def check_signature(signature, appointment):
    try:
        pisa_pk_der = load_key_file_data(config.get("PISA_PUBLIC_KEY"))
        pisa_pk = Cryptographer.load_public_key_der(pisa_pk_der)

        if pisa_pk is None:
            logger.error("Failed to deserialize the public key. It might be in an unsupported format")
            return False

        return Cryptographer.verify(appointment.serialize(), signature, pisa_pk)

    except FileNotFoundError:
        logger.error("Pisa's public key file not found. Please check your settings")
        return False

    except IOError as e:
        logger.error("I/O error", errno=e.errno, error=e.strerror)
        return False


def get_appointment(args):
    if not args:
        logger.error("No arguments were given")
        return None

    arg_opt = args.pop(0)

    if arg_opt in ["-h", "--help"]:
        sys.exit(help_get_appointment())
    else:
        locator = arg_opt
        valid_locator = check_locator_format(locator)

    if not valid_locator:
        logger.error("The provided locator is not valid", locator=locator)
        return None

    get_appointment_endpoint = "http://{}:{}/get_appointment".format(pisa_api_server, pisa_api_port)
    parameters = "?locator={}".format(locator)

    try:
        r = requests.get(url=get_appointment_endpoint + parameters, timeout=5)
        logger.info("Appointment response returned from server: {}".format(r.json()))
        return r.json()

    except ConnectTimeout:
        logger.error("Can't connect to pisa API. Connection timeout")
        return None

    except ConnectionError:
        logger.error("Can't connect to pisa API. Server cannot be reached")
        return None


def get_appointment_signature(appointment):
    try:
        sk_der = load_key_file_data(config.get("CLI_PRIVATE_KEY"))
        cli_sk = Cryptographer.load_private_key_der(sk_der)

        signature = Cryptographer.sign(appointment.serialize(), cli_sk)

        return signature

    except ValueError:
        logger.error("Failed to deserialize the public key. It might be in an unsupported format")
        return False

    except FileNotFoundError:
        logger.error("Client's private key file not found. Please check your settings")
        return False

    except IOError as e:
        logger.error("I/O error", errno=e.errno, error=e.strerror)
        return False


def get_pk():
    try:
        cli_pk_der = load_key_file_data(config.get("CLI_PUBLIC_KEY"))
        hex_pk_der = binascii.hexlify(cli_pk_der)

        return hex_pk_der

    except FileNotFoundError:
        logger.error("Client's public key file not found. Please check your settings")
        return False

    except IOError as e:
        logger.error("I/O error", errno=e.errno, error=e.strerror)
        return False

    except binascii.Error as e:
        logger.error("Could not successfully encode public key as hex: ", e)
        return False


def show_usage():
    return (
        "USAGE: "
        "\n\tpython pisa-cli.py [global options] command [command options] [arguments]"
        "\n\nCOMMANDS:"
        "\n\tadd_appointment \tRegisters a json formatted appointment to the PISA server."
        "\n\tget_appointment \tGets json formatted data about an appointment from the PISA server."
        "\n\thelp \t\t\tShows a list of commands or help for a specific command."
        "\n\nGLOBAL OPTIONS:"
        "\n\t-s, --server \tAPI server where to send the requests. Defaults to btc.pisa.watch (modifiable in "
        "__init__.py)"
        "\n\t-p, --port \tAPI port where to send the requests. Defaults to 9814 (modifiable in __init__.py)"
        "\n\t-d, --debug \tshows debug information and stores it in pisa.log"
        "\n\t-h --help \tshows this message."
    )


if __name__ == "__main__":
    pisa_api_server = config.get("DEFAULT_PISA_API_SERVER")
    pisa_api_port = config.get("DEFAULT_PISA_API_PORT")
    commands = ["add_appointment", "get_appointment", "help"]
    testing_commands = ["generate_dummy_appointment"]

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
                    get_appointment(args)

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

            # FIXME: testing command, not for production
            elif command in testing_commands:
                if command == "generate_dummy_appointment":
                    generate_dummy_appointment()

            else:
                logger.error("Unknown command. Use help to check the list of available commands")

        else:
            logger.error("No command provided. Use help to check the list of available commands")

    except GetoptError as e:
        logger.error("{}".format(e))

    except json.JSONDecodeError as e:
        logger.error("Non-JSON encoded appointment passed as parameter")
