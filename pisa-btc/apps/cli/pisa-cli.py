import re
import os
import sys
import json
import logging
import requests
from sys import argv
from getopt import getopt, GetoptError
from hashlib import sha256
from binascii import unhexlify
from requests import ConnectTimeout, ConnectionError
from apps.cli import DEFAULT_PISA_API_SERVER, DEFAULT_PISA_API_PORT, CLIENT_LOG_FILE
from apps.cli.blob import Blob
from apps.cli.help import help_add_appointment, help_get_appointment


def add_appointment(args, debug):
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
                        sys.exit("Can't find file " + fin)
                else:
                    sys.exit("No file provided as appointment. " + use_help)
            else:
                appointment_data = json.loads(arg_opt)

        except json.JSONDecodeError:
            sys.exit("Non-JSON encoded data provided as appointment. " + use_help)

    else:
        sys.exit("No appointment data provided. " + use_help)

    valid_locator = check_txid_format(appointment_data.get('tx_id'))

    if valid_locator:
        add_appointment_endpoint = "http://{}:{}".format(pisa_api_server, pisa_api_port)
        appointment = build_appointment(appointment_data.get('tx'), appointment_data.get('tx_id'),
                                        appointment_data.get('start_time'), appointment_data.get('end_time'),
                                        appointment_data.get('dispute_delta'), debug, logging)

        if debug:
            logging.info("[Client] sending appointment to PISA")

        try:
            r = requests.post(url=add_appointment_endpoint, json=json.dumps(appointment), timeout=5)

            if debug:
                logging.info("[Client] {} (code: {})".format(r.text, r.status_code))
            else:
                print("{} (code: {}).".format(r.text, r.status_code))

        except ConnectTimeout:
            if debug:
                logging.info("[Client] can't connect to pisa API. Connection timeout")
            else:
                sys.exit("Can't connect to pisa API. Connection timeout.")

        except ConnectionError:
            if debug:
                logging.info("[Client] can't connect to pisa API. Server cannot be reached")
            else:
                sys.exit("Can't connect to pisa API. Server cannot be reached.")
    else:
        raise sys.exit("The provided locator is not valid.")


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
                r = requests.get(url=get_appointment_endpoint+parameters, timeout=5)

                print(json.dumps(r.json(), indent=4, sort_keys=True))

            except ConnectTimeout:
                if debug:
                    logging.info("[Client] can't connect to pisa API. Connection timeout")
                else:
                    sys.exit("Can't connect to pisa API. Connection timeout.")

            except ConnectionError:
                if debug:
                    logging.info("[Client] can't connect to pisa API. Server cannot be reached")
                else:
                    sys.exit("Can't connect to pisa API. Server cannot be reached.")

        else:
            sys.exit("The provided locator is not valid.")
    else:
        raise sys.exit("The provided locator is not valid.")


def build_appointment(tx, tx_id, start_block, end_block, dispute_delta, debug, logging):
    locator = sha256(unhexlify(tx_id)).hexdigest()

    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    # FIXME: The blob data should contain more things that just the transaction. Leaving like this for now.
    blob = Blob(tx, cipher, hash_function)

    # FIXME: tx_id should not be necessary (can be derived from tx SegWit-like). Passing it for now
    encrypted_blob = blob.encrypt(tx_id, debug, logging)

    appointment = {"locator": locator, "start_time": start_block, "end_time": end_block,
                   "dispute_delta": dispute_delta, "encrypted_blob": encrypted_blob, "cipher": cipher, "hash_function":
                   hash_function}

    return appointment


def check_txid_format(txid):
    if len(txid) != 64:
        raise sys.exit("locator does not matches the expected size (32-byte / 64 hex chars).")

    return re.search(r'^[0-9A-Fa-f]+$', txid) is not None


def show_usage():
    return('USAGE: '
           '\n\tpython pisa-cli.py [global options] command [command options] [arguments]'
           '\n\nCOMMANDS:'
           '\n\tadd_appointment \tRegisters a json formatted appointment to the PISA server.'
           '\n\tget_appointment \tGets json formatted data about an appointment from the PISA server.'
           '\n\thelp \t\t\tShows a list of commands or help for a specific command.'

           '\n\nGLOBAL OPTIONS:'
           '\n\t-s, --server \tAPI server where to send the requests. Defaults to 35.177.25.32 (modifiable in '
           '__init__.py)'
           '\n\t-p, --port \tAPI port where to send the requests. Defaults to 9814 (modifiable in __init__.py)'
           '\n\t-d, --debug \tshows debug information and stores it in pisa.log'
           '\n\t-h --help \tshows this message.')


if __name__ == '__main__':
    debug = False
    pisa_api_server = DEFAULT_PISA_API_SERVER
    pisa_api_port = DEFAULT_PISA_API_PORT
    commands = ['add_appointment', 'get_appointment', 'help']

    # Configure logging
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO, handlers=[
        logging.FileHandler(CLIENT_LOG_FILE),
        logging.StreamHandler()
    ])

    try:
        opts, args = getopt(argv[1:], 's:p:dh', ['server', 'port', 'debug', 'help'])

        for opt, arg in opts:
            if opt in ['-s', 'server']:
                if arg:
                    pisa_api_server = arg

            if opt in ['-p', '--port']:
                if arg:
                    pisa_api_port = int(arg)

            if opt in ['-d', '--debug']:
                debug = True

            if opt in ['-h', '--help']:
                sys.exit(show_usage())

        if args:
            command = args.pop(0)

            if command in commands:
                if command == 'add_appointment':
                    add_appointment(args, debug)

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
                            sys.exit("Unknown command. Use help to check the list of available commands.")
                    else:
                        sys.exit(show_usage())

            else:
                sys.exit("Unknown command. Use help to check the list of available commands.")
        else:
            sys.exit("No command provided. Use help to check the list of available commands.")

    except GetoptError as e:
        print(e)
    except json.JSONDecodeError as e:
        print('Non-JSON encoded appointment passed as parameter.')


