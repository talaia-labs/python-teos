import os
import sys
import time
import json
import requests
from sys import argv
from uuid import uuid4
from coincurve import PublicKey
from getopt import getopt, GetoptError
from requests import Timeout, ConnectionError
from requests.exceptions import MissingSchema, InvalidSchema, InvalidURL

from cli.exceptions import TowerResponseError
from cli import DEFAULT_CONF, DATA_DIR, CONF_FILE_NAME, LOG_PREFIX
from cli.help import show_usage, help_add_appointment, help_get_appointment, help_register, help_get_all_appointments

from common import constants
from common.logger import Logger
from common.appointment import Appointment
from common.config_loader import ConfigLoader
from common.cryptographer import Cryptographer
from common.tools import setup_logging, setup_data_folder
from common.exceptions import InvalidKey, InvalidParameter, SignatureError
from common.tools import is_256b_hex_str, is_locator, compute_locator, is_compressed_pk

logger = Logger(actor="Client", log_name_prefix=LOG_PREFIX)


def register(user_id, teos_url):
    """
    Registers the user to the tower.

    Args:
        user_id (:obj:`str`): a 33-byte hex-encoded compressed public key representing the user.
        teos_url (:obj:`str`): the teos base url.

    Returns:
        :obj:`dict`: a dictionary containing the tower response if the registration succeeded.

    Raises:
        :obj:`InvalidParameter <cli.exceptions.InvalidParameter>`: if `user_id` is invalid.
        :obj:`ConnectionError`: if the client cannot connect to the tower.
        :obj:`TowerResponseError <cli.exceptions.TowerResponseError>`: if the tower responded with an error, or the
        response was invalid.
    """

    if not is_compressed_pk(user_id):
        raise InvalidParameter("The cli public key is not valid")

    # Send request to the server.
    register_endpoint = "{}/register".format(teos_url)
    data = {"public_key": user_id}

    logger.info("Registering in the Eye of Satoshi")
    response = process_post_response(post_request(data, register_endpoint))

    return response


def add_appointment(appointment_data, user_sk, teos_id, teos_url):
    """
    Manages the add_appointment command.

    The life cycle of the function is as follows:
        - Check that the given commitment_txid is correct (proper format and not missing)
        - Check that the transaction is correct (not missing)
        - Create the appointment locator and encrypted blob from the commitment_txid and the penalty_tx
        - Sign the appointment
        - Send the appointment to the tower
        - Wait for the response
        - Check the tower's response and signature

    Args:
        appointment_data (:obj:`dict`): a dictionary containing the appointment data.
        user_sk (:obj:`PrivateKey`): the user's private key.
        teos_id (:obj:`str`): the tower's compressed public key.
        teos_url (:obj:`str`): the teos base url.

    Returns:
        :obj:`tuple`: A tuple (`:obj:Appointment <common.appointment.Appointment>`, :obj:`str`) containing the
        appointment and the tower's signature.

    Raises:
        :obj:`InvalidParameter <cli.exceptions.InvalidParameter>`: if `appointment_data` or any of its fields is
        invalid.
        :obj:`ValueError`: if the appointment cannot be signed.
        :obj:`ConnectionError`: if the client cannot connect to the tower.
        :obj:`TowerResponseError <cli.exceptions.TowerResponseError>`: if the tower responded with an error, or the
        response was invalid.
    """

    if not appointment_data:
        raise InvalidParameter("The provided appointment JSON is empty")

    tx_id = appointment_data.get("tx_id")
    tx = appointment_data.get("tx")

    if not is_256b_hex_str(tx_id):
        raise InvalidParameter("The provided locator is wrong or missing")

    if not tx:
        raise InvalidParameter("The provided data is missing the transaction")

    appointment_data["locator"] = compute_locator(tx_id)
    appointment_data["encrypted_blob"] = Cryptographer.encrypt(tx, tx_id)
    appointment = Appointment.from_dict(appointment_data)
    signature = Cryptographer.sign(appointment.serialize(), user_sk)

    data = {"appointment": appointment.to_dict(), "signature": signature}

    # Send appointment to the server.
    logger.info("Sending appointment to the Eye of Satoshi")
    add_appointment_endpoint = "{}/add_appointment".format(teos_url)
    response = process_post_response(post_request(data, add_appointment_endpoint))

    tower_signature = response.get("signature")
    # Check that the server signed the appointment as it should.
    if not tower_signature:
        raise TowerResponseError("The response does not contain the signature of the appointment")

    rpk = Cryptographer.recover_pk(appointment.serialize(), tower_signature)
    if teos_id != Cryptographer.get_compressed_pk(rpk):
        raise TowerResponseError("The returned appointment's signature is invalid")

    logger.info("Appointment accepted and signed by the Eye of Satoshi")
    logger.info("Remaining slots: {}".format(response.get("available_slots")))
    logger.info("Start block: {}".format(response.get("start_block")))

    return appointment, tower_signature


def get_appointment(locator, user_sk, teos_id, teos_url):
    """
    Gets information about an appointment from the tower.

    Args:
        locator (:obj:`str`): the appointment locator used to identify it.
        user_sk (:obj:`PrivateKey`): the user's private key.
        teos_id (:obj:`PublicKey`): the tower's compressed public key.
        teos_url (:obj:`str`): the teos base url.

    Returns:
        :obj:`dict`: a dictionary containing the appointment data.

    Raises:
        :obj:`InvalidParameter <cli.exceptions.InvalidParameter>`: if `appointment_data` or any of its fields is
        invalid.
        :obj:`ConnectionError`: if the client cannot connect to the tower.
        :obj:`TowerResponseError <cli.exceptions.TowerResponseError>`: if the tower responded with an error, or the
        response was invalid.
    """

    # FIXME: All responses from the tower should be signed. Not using teos_id atm.

    if not is_locator(locator):
        raise InvalidParameter("The provided locator is not valid", locator=locator)

    message = "get appointment {}".format(locator)
    signature = Cryptographer.sign(message.encode(), user_sk)
    data = {"locator": locator, "signature": signature}

    # Send request to the server.
    get_appointment_endpoint = "{}/get_appointment".format(teos_url)
    logger.info("Requesting appointment from the Eye of Satoshi")
    response = process_post_response(post_request(data, get_appointment_endpoint))

    return response


def get_all_appointments(teos_url):
    """
    Gets information about all appointments stored in the tower, if the user requesting the data is an administrator.

    Args:
        teos_url (:obj:`str`): the teos base url.

    Returns:
        :obj:`dict` a dictionary containing all the appointments stored by the Responder and Watcher if the tower
        responds.
    """

    get_all_appointments_endpoint = "{}/get_all_appointments".format(teos_url)

    try:
        response = requests.get(url=get_all_appointments_endpoint, timeout=5)

        if response.status_code != constants.HTTP_OK:
            logger.error("The server returned an error", status_code=response.status_code, reason=response.reason)
            return None

        response_json = json.dumps(response.json(), indent=4, sort_keys=True)
        return response_json

    except ConnectionError:
        logger.error("Can't connect to the Eye of Satoshi's API. Server cannot be reached")
        return None

    except requests.exceptions.Timeout:
        logger.error("The request timed out")
        return None


def delete_appointment(locator, cli_sk, teos_pk, teos_url):
    """
    Deletes information about an appointment from the tower.

    Args:
        locator (:obj:`str`): the locator used to identify the appointment.
        cli_sk (:obj:`PrivateKey`): the client's private key.
        teos_pk (:obj:`PublicKey`): the tower's public key.
        teos_url (:obj:`str`): the teos base url.

    Returns:
        :obj:`dict` or :obj:`None`: a dictionary containing the appointment data if the locator is valid and the tower
        responds. ``None`` otherwise.

    Raises:
        :obj:`InvalidParameter <cli.exceptions.InvalidParameter>`: if ``locator`` is invalid.
        :obj:`ConnectionError`: if the client cannot connect to the tower.
        :obj:`TowerResponseError <cli.exceptions.TowerResponseError>`: if the tower responded with an error, or the
        response was invalid.
    """

    # FIXME: All responses from the tower should be signed. Not using teos_pk atm.

    if not is_locator(locator):
        raise InvalidParameter("The provided locator is not valid", locator=locator)

    message = "delete appointment {}".format(locator)
    signature = Cryptographer.sign(message.encode(), cli_sk)
    data = {"locator": locator, "signature": signature}

    # Send request to the server.
    delete_appointment_endpoint = "{}/delete_appointment".format(teos_url)
    logger.info("Sending appointment deletion request to the Eye of Satoshi")
    server_response = post_request(data, delete_appointment_endpoint)

    response_json = process_post_response(server_response)

    return response_json


def load_keys(teos_pk_path, user_sk_path):
    """
    Loads all the keys required so sign, send, and verify the appointment.

    Args:
        teos_pk_path (:obj:`str`): path to the tower's public key file.
        user_sk_path (:obj:`str`): path to the user's private key file.

    Returns:
        :obj:`tuple`: a three-item tuple containing a ``str``, a ``PrivateKey`` and a ``str``
        representing the tower id (compressed pk), user sk and user id (compressed pk) respectively.

    Raises:
        :obj:`InvalidKey <cli.exceptions.InvalidKey>`: if any of the keys is invalid or cannot be loaded.
    """

    if not teos_pk_path:
        raise InvalidKey("TEOS's public key file not found. Please check your settings")

    if not user_sk_path:
        raise InvalidKey("Client's private key file not found. Please check your settings")

    try:
        teos_pk_der = Cryptographer.load_key_file(teos_pk_path)
        teos_id = Cryptographer.get_compressed_pk(PublicKey(teos_pk_der))

    except (InvalidParameter, InvalidKey, ValueError):
        raise InvalidKey("TEOS public key cannot be loaded")

    try:
        user_sk_der = Cryptographer.load_key_file(user_sk_path)
        user_sk = Cryptographer.load_private_key_der(user_sk_der)

    except (InvalidParameter, InvalidKey):
        raise InvalidKey("Client private key is invalid or cannot be parsed")

    try:
        user_id = Cryptographer.get_compressed_pk(user_sk.public_key)

    except (InvalidParameter, InvalidKey):
        raise InvalidKey("Client public key cannot be loaded")

    return teos_id, user_sk, user_id


def post_request(data, endpoint):
    """
    Sends a post request to the tower.

    Args:
        data (:obj:`dict`): a dictionary containing the data to be posted.
        endpoint (:obj:`str`): the endpoint to send the post request.

    Returns:
        :obj:`dict`: a json-encoded dictionary with the server response if the data can be posted.

    Raises:
        :obj:`ConnectionError`: if the client cannot connect to the tower.
    """

    try:
        return requests.post(url=endpoint, json=data, timeout=5)

    except Timeout:
        message = "Cannot connect to the Eye of Satoshi's API. Connection timeout"

    except ConnectionError:
        message = "Cannot connect to the Eye of Satoshi's API. Server cannot be reached"

    except (InvalidSchema, MissingSchema, InvalidURL):
        message = "Invalid URL. No schema, or invalid schema, found ({})".format(endpoint)

    raise ConnectionError(message)


def process_post_response(response):
    """
    Processes the server response to a post request.

    Args:
        response (:obj:`requests.models.Response`): a ``Response`` object obtained from the request.

    Returns:
        :obj:`dict`: a dictionary containing the tower's response data if the response type is
        ``HTTP_OK``.

    Raises:
        :obj:`TowerResponseError <cli.exceptions.TowerResponseError>`: if the tower responded with an error, or the
        response was invalid.
    """

    try:
        response_json = response.json()

    except (json.JSONDecodeError, AttributeError):
        raise TowerResponseError(
            "The server returned a non-JSON response", status_code=response.status_code, reason=response.reason
        )

    if response.status_code != constants.HTTP_OK:
        raise TowerResponseError(
            "The server returned an error", status_code=response.status_code, reason=response.reason, data=response_json
        )

    return response_json


def parse_add_appointment_args(args):
    """
    Parses the arguments of the add_appointment command.

    Args:
        args (:obj:`list`): a list of command line arguments that must contain a json encoded appointment, or the file
        option and the path to a file containing a json encoded appointment.

    Returns:
        :obj:`dict`: A dictionary containing the appointment data.

    Raises:
        :obj:`InvalidParameter <cli.exceptions.InvalidParameter>`: if the appointment data is not JSON encoded.
        :obj:`FileNotFoundError`: if -f is passed and the appointment file is not found.
        :obj:`IOError`: if -f was passed and the file cannot be read.
    """

    use_help = "Use 'help add_appointment' for help of how to use the command"

    if not args:
        raise InvalidParameter("No appointment data provided. " + use_help)

    arg_opt = args.pop(0)

    try:
        if arg_opt in ["-h", "--help"]:
            sys.exit(help_add_appointment())

        if arg_opt in ["-f", "--file"]:
            fin = args.pop(0)
            if not os.path.isfile(fin):
                raise FileNotFoundError("Cannot find {}".format(fin))

            try:
                with open(fin) as f:
                    appointment_data = json.load(f)

            except IOError as e:
                raise IOError("Cannot read appointment file. {}".format(str(e)))

        else:
            appointment_data = json.loads(arg_opt)

    except json.JSONDecodeError:
        raise InvalidParameter("Non-JSON encoded data provided as appointment. " + use_help)

    return appointment_data


def save_appointment_receipt(appointment, signature, appointments_folder_path):
    """
    Saves an appointment receipt to disk. A receipt consists of an appointment and a signature from the tower.

    Args:
        appointment (:obj:`Appointment <common.appointment.Appointment>`): the appointment to be saved on disk.
        signature (:obj:`str`): the signature of the appointment performed by the tower.
        appointments_folder_path (:obj:`str`): the path to the appointments folder.

    Raises:
        IOError: if an error occurs whilst writing the file on disk.
    """

    # Create the appointments directory if it doesn't already exist
    os.makedirs(appointments_folder_path, exist_ok=True)

    timestamp = int(time.time())
    locator = appointment["locator"]
    uuid = uuid4().hex  # prevent filename collisions

    filename = "{}/appointment-{}-{}-{}.json".format(appointments_folder_path, timestamp, locator, uuid)
    data = {"appointment": appointment, "signature": signature}

    try:
        with open(filename, "w") as f:
            json.dump(data, f)
            logger.info("Appointment saved at {}".format(filename))

    except IOError as e:
        raise IOError("There was an error while saving the appointment. {}".format(e))


def main(command, args, command_line_conf):
    # Loads config and sets up the data folder and log file
    config_loader = ConfigLoader(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF, command_line_conf)
    config = config_loader.build_config()

    setup_data_folder(DATA_DIR)
    setup_logging(config.get("LOG_FILE"), LOG_PREFIX)

    # Set the teos url
    teos_url = "{}:{}".format(config.get("API_CONNECT"), config.get("API_PORT"))
    # If an http or https prefix if found, leaves the server as is. Otherwise defaults to http.
    if not teos_url.startswith("http"):
        teos_url = "http://" + teos_url

    try:
        teos_id, user_sk, user_id = load_keys(config.get("TEOS_PUBLIC_KEY"), config.get("CLI_PRIVATE_KEY"))

        if command == "register":
            register_data = register(user_id, teos_url)
            logger.info("Registration succeeded. Available slots: {}".format(register_data.get("available_slots")))

        if command == "add_appointment":
            appointment_data = parse_add_appointment_args(args)
            appointment, signature = add_appointment(appointment_data, user_sk, teos_id, teos_url)
            save_appointment_receipt(appointment.to_dict(), signature, config.get("APPOINTMENTS_FOLDER_NAME"))

        elif command == "get_appointment":
            if not args:
                logger.error("No arguments were given")

            else:
                arg_opt = args.pop(0)

                if arg_opt in ["-h", "--help"]:
                    sys.exit(help_get_appointment())

                appointment_data = get_appointment(arg_opt, user_sk, teos_id, teos_url)
                if appointment_data:
                    print(appointment_data)

        elif command == "get_all_appointments":
            appointment_data = get_all_appointments(teos_url)
            if appointment_data:
                print(appointment_data)

        elif command == "help":
            if args:
                command = args.pop(0)

                if command == "register":
                    sys.exit(help_register())

                if command == "add_appointment":
                    sys.exit(help_add_appointment())

                elif command == "get_appointment":
                    sys.exit(help_get_appointment())

                elif command == "get_all_appointments":
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
    commands = ["register", "add_appointment", "get_appointment", "get_all_appointments", "help"]

    try:
        opts, args = getopt(argv[1:], "h", ["apiconnect=", "apiport=", "help"])

        for opt, arg in opts:
            if opt in ["--apiconnect"]:
                if arg:
                    command_line_conf["API_CONNECT"] = arg

            if opt in ["--apiport"]:
                if arg:
                    try:
                        command_line_conf["API_PORT"] = int(arg)
                    except ValueError:
                        sys.exit("port must be an integer")

            if opt in ["-h", "--help"]:
                sys.exit(show_usage())

        command = args.pop(0) if args else None
        if command in commands:
            main(command, args, command_line_conf)
        elif not command:
            logger.error("No command provided. Use help to check the list of available commands")
        else:
            logger.error("Unknown command. Use help to check the list of available commands")

    except GetoptError as e:
        logger.error("{}".format(e))
