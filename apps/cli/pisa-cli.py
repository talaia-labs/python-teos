import re
import os
import sys
import json
import requests
import time
from sys import argv
from hashlib import sha256
from binascii import unhexlify
from getopt import getopt, GetoptError
from requests import ConnectTimeout, ConnectionError
from uuid import uuid4


from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm

from apps.cli.blob import Blob
from apps.cli.help import help_add_appointment, help_get_appointment
from apps.cli import DEFAULT_PISA_API_SERVER, DEFAULT_PISA_API_PORT, PISA_PUBLIC_KEY, APPOINTMENTS_FOLDER_NAME
from apps.cli import logger


HTTP_OK = 200


# FIXME: TESTING ENDPOINT, WON'T BE THERE IN PRODUCTION
def generate_dummy_appointment():
    get_block_count_end_point = "http://{}:{}/get_block_count".format(pisa_api_server, pisa_api_port)
    r = requests.get(url=get_block_count_end_point, timeout=5)

    current_height = r.json().get("block_count")

    dummy_appointment_data = {"tx": os.urandom(192).hex(), "tx_id": os.urandom(32).hex(),
                              "start_time": current_height + 5, "end_time": current_height + 10, "dispute_delta": 20}

    print('Generating dummy appointment data:''\n\n' + json.dumps(dummy_appointment_data, indent=4, sort_keys=True))

    json.dump(dummy_appointment_data, open('dummy_appointment_data.json', 'w'))

    print('\nData stored in dummy_appointment_data.json')


# Loads Pisa's public key from disk and verifies that the appointment signature is a valid signature from Pisa,
# returning True or False accordingly.
# Will raise NotFoundError or IOError if the attempts to open and read the public key file fail.
# Will raise ValueError if it the public key file was present but it failed to be deserialized.
def is_appointment_signature_valid(appointment, signature):
    # Load the key from disk
    try:
        with open(PISA_PUBLIC_KEY, "r") as key_file:
            pubkey_pem = key_file.read().encode("utf-8")
            pisa_public_key = load_pem_public_key(pubkey_pem, backend=default_backend())
    except UnsupportedAlgorithm:
        raise ValueError("Could not deserialize the public key (unsupported algorithm).")

    try:
        sig_bytes = unhexlify(signature.encode('utf-8'))
        data = json.dumps(appointment, sort_keys=True, separators=(',', ':')).encode("utf-8")
        pisa_public_key.verify(sig_bytes, data, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        return False

    return True


# Makes sure that the folder APPOINTMENTS_FOLDER_NAME exists, then saves the appointment and signature in it.
def save_signed_appointment(appointment, signature):
    # Create the appointments directory if it doesn't already exist
    try:
        os.makedirs(APPOINTMENTS_FOLDER_NAME)
    except FileExistsError:
        # directory already exists, this is fine
        pass

    timestamp = int(time.time()*1000)
    locator = appointment['locator']
    uuid = uuid4()  # prevent filename collisions
    filename = "{}/appointment-{}-{}-{}.json".format(APPOINTMENTS_FOLDER_NAME, timestamp, locator, uuid)
    data = {"appointment": appointment, "signature": signature}

    with open(filename, "w") as f:
        json.dump(data, f)


def add_appointment(args):
    appointment_data = None
    use_help = "Use 'help add_appointment' for help of how to use the command."

    if args:
        arg_opt = args.pop(0)

        try:
            if arg_opt in ['-h', '--help']:
                sys.exit(help_add_appointment())

            if arg_opt in ['-f', '--file']:
                if args:
                    fin = args.pop(0)
                    if os.path.isfile(fin):
                        appointment_data = json.load(open(fin))
                    else:
                        logger.error("Can't find file " + fin)
                else:
                    logger.error("No file provided as appointment. " + use_help)
            else:
                appointment_data = json.loads(arg_opt)

        except json.JSONDecodeError:
            logger.error("Non-JSON encoded data provided as appointment. " + use_help)

        if appointment_data:
            valid_locator = check_txid_format(appointment_data.get('tx_id'))

            if valid_locator:
                add_appointment_endpoint = "http://{}:{}".format(pisa_api_server, pisa_api_port)
                appointment = build_appointment(appointment_data.get('tx'), appointment_data.get('tx_id'),
                                                appointment_data.get('start_time'), appointment_data.get('end_time'),
                                                appointment_data.get('dispute_delta'))
                appointment_json = json.dumps(appointment, sort_keys=True, separators=(',', ':'))

                logger.info("Sending appointment to PISA")

                try:
                    r = requests.post(url=add_appointment_endpoint, json=appointment_json, timeout=5)

                    response_json = r.json()

                except json.JSONDecodeError:
                    logger.error("The response was not valid JSON.")
                    return

                except ConnectTimeout:
                    logger.error("Can't connect to pisa API. Connection timeout.")
                    return

                except ConnectionError:
                    logger.error("Can't connect to pisa API. Server cannot be reached.")
                    return

                if r.status_code == HTTP_OK:
                    if 'signature' not in response_json:
                        logger.error("The response does not contain the signature of the appointment.")
                    else:
                        signature = response_json['signature']
                        # verify that the returned signature is valid
                        try:
                            is_sig_valid = is_appointment_signature_valid(appointment, signature)
                        except ValueError:
                            logger.error("Failed to deserialize the public key. It might be in an unsupported format.")
                            return
                        except FileNotFoundError:
                            logger.error("Pisa's public key file not found. Please check your settings.")
                            return
                        except IOError as e:
                            logger.error("I/O error({}): {}".format(e.errno, e.strerror))
                            return

                        if is_sig_valid:
                            logger.info("Appointment accepted and signed by Pisa.")
                            # all good, store appointment and signature
                            try:
                                save_signed_appointment(appointment, signature)
                            except OSError as e:
                                logger.error("There was an error while saving the appointment: {}".format(e))
                        else:
                            logger.error("The returned appointment's signature is invalid.")

                else:
                    if 'error' not in response_json:
                        logger.error("The server returned status code {}, but no error description."
                                     .format(r.status_code))
                    else:
                        error = r.json()['error']
                        logger.error("The server returned status code {}, and the following error: {}."
                                     .format(r.status_code, error))

            else:
                logger.error("The provided locator is not valid.")
    else:
        logger.error("No appointment data provided. " + use_help)


def get_appointment(args):
    if args:
        arg_opt = args.pop(0)

        if arg_opt in ['-h', '--help']:
            sys.exit(help_get_appointment())
        else:
            locator = arg_opt
            valid_locator = check_txid_format(locator)

        if valid_locator:
            get_appointment_endpoint = "http://{}:{}/get_appointment".format(pisa_api_server, pisa_api_port)
            parameters = "?locator={}".format(locator)
            try:
                r = requests.get(url=get_appointment_endpoint + parameters, timeout=5)

                print(json.dumps(r.json(), indent=4, sort_keys=True))

            except ConnectTimeout:
                logger.error("Can't connect to pisa API. Connection timeout.")

            except ConnectionError:
                logger.error("Can't connect to pisa API. Server cannot be reached.")

        else:
            logger.error("The provided locator is not valid.")

    else:
        logger.error("The provided locator is not valid.")


def build_appointment(tx, tx_id, start_time, end_time, dispute_delta):
    locator = sha256(unhexlify(tx_id)).hexdigest()

    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    # FIXME: The blob data should contain more things that just the transaction. Leaving like this for now.
    blob = Blob(tx, cipher, hash_function)
    encrypted_blob = blob.encrypt(tx_id)

    appointment = {
        'locator': locator, 'start_time': start_time, 'end_time': end_time, 'dispute_delta': dispute_delta,
        'encrypted_blob': encrypted_blob, 'cipher': cipher, 'hash_function': hash_function}

    return appointment


def check_txid_format(txid):
    if len(txid) != 64:
        sys.exit("locator does not matches the expected size (32-byte / 64 hex chars).")

    # TODO: #12-check-txid-regexp
    return re.search(r'^[0-9A-Fa-f]+$', txid) is not None


def show_usage():
    return ('USAGE: '
            '\n\tpython pisa-cli.py [global options] command [command options] [arguments]'
            '\n\nCOMMANDS:'
            '\n\tadd_appointment \tRegisters a json formatted appointment to the PISA server.'
            '\n\tget_appointment \tGets json formatted data about an appointment from the PISA server.'
            '\n\thelp \t\t\tShows a list of commands or help for a specific command.'

            '\n\nGLOBAL OPTIONS:'
            '\n\t-s, --server \tAPI server where to send the requests. Defaults to btc.pisa.watch (modifiable in '
            '__init__.py)'
            '\n\t-p, --port \tAPI port where to send the requests. Defaults to 9814 (modifiable in __init__.py)'
            '\n\t-d, --debug \tshows debug information and stores it in pisa.log'
            '\n\t-h --help \tshows this message.')


if __name__ == '__main__':
    pisa_api_server = DEFAULT_PISA_API_SERVER
    pisa_api_port = DEFAULT_PISA_API_PORT
    commands = ['add_appointment', 'get_appointment', 'help']
    testing_commands = ['generate_dummy_appointment']

    try:
        opts, args = getopt(argv[1:], 's:p:h', ['server', 'port', 'help'])

        for opt, arg in opts:
            if opt in ['-s', 'server']:
                if arg:
                    pisa_api_server = arg

            if opt in ['-p', '--port']:
                if arg:
                    pisa_api_port = int(arg)

            if opt in ['-h', '--help']:
                sys.exit(show_usage())

        if args:
            command = args.pop(0)

            if command in commands:
                if command == 'add_appointment':
                    add_appointment(args)

                elif command == 'get_appointment':
                    get_appointment(args)

                elif command == 'help':
                    if args:
                        command = args.pop(0)

                        if command == 'add_appointment':
                            sys.exit(help_add_appointment())

                        elif command == "get_appointment":
                            sys.exit(help_get_appointment())

                        else:
                            logger.error("Unknown command. Use help to check the list of available commands")

                    else:
                        sys.exit(show_usage())

            # FIXME: testing command, not for production
            elif command in testing_commands:
                if command == 'generate_dummy_appointment':
                    generate_dummy_appointment()

            else:
                logger.error("Unknown command. Use help to check the list of available commands")

        else:
            logger.error("No command provided. Use help to check the list of available commands.")

    except GetoptError as e:
        logger.error("{}".format(e))

    except json.JSONDecodeError as e:
        logger.error("Non-JSON encoded appointment passed as parameter.")
