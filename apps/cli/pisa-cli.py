import re
import os
import sys
import json
import logging
import requests
from sys import argv
from hashlib import sha256
from binascii import unhexlify
from getopt import getopt, GetoptError
from requests import ConnectTimeout, ConnectionError

from apps.cli.blob import Blob
from apps.cli.help import help_add_appointment, help_get_appointment
from apps.cli import DEFAULT_PISA_API_SERVER, DEFAULT_PISA_API_PORT


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
                        logging.error("[Client] can't find file " + fin)
                else:
                    logging.error("[Client] no file provided as appointment. " + use_help)
            else:
                appointment_data = json.loads(arg_opt)

        except json.JSONDecodeError:
            logging.error("[Client] non-JSON encoded data provided as appointment. " + use_help)

        if appointment_data:
            valid_locator = check_txid_format(appointment_data.get('tx_id'))

            if valid_locator:
                add_appointment_endpoint = "http://{}:{}".format(pisa_api_server, pisa_api_port)
                appointment = build_appointment(appointment_data.get('tx'), appointment_data.get('tx_id'),
                                                appointment_data.get('start_time'), appointment_data.get('end_time'),
                                                appointment_data.get('dispute_delta'))

                logging.info("[Client] sending appointment to PISA")

                try:
                    r = requests.post(url=add_appointment_endpoint, json=json.dumps(appointment), timeout=5)

                    logging.info("[Client] {} (code: {}).".format(r.text, r.status_code))

                except ConnectTimeout:
                    logging.error("[Client] can't connect to pisa API. Connection timeout.")

                except ConnectionError:
                    logging.error("[Client] can't connect to pisa API. Server cannot be reached.")
            else:
                logging.error("[Client] the provided locator is not valid.")
    else:
        logging.error("[Client] no appointment data provided. " + use_help)


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
                logging.error("[Client] can't connect to pisa API. Connection timeout.")

            except ConnectionError:
                logging.error("[Client] can't connect to pisa API. Server cannot be reached.")

        else:
            logging.error("[Client] the provided locator is not valid.")

    else:
        logging.error("[Client] the provided locator is not valid.")


def build_appointment(tx, tx_id, start_block, end_block, dispute_delta):
    locator = sha256(unhexlify(tx_id)).hexdigest()

    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    # FIXME: The blob data should contain more things that just the transaction. Leaving like this for now.
    blob = Blob(tx, cipher, hash_function)
    encrypted_blob = blob.encrypt(tx_id)

    appointment = {"locator": locator, "start_time": start_block, "end_time": end_block,
                   "dispute_delta": dispute_delta, "encrypted_blob": encrypted_blob, "cipher": cipher, "hash_function":
                       hash_function}

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
                            logging.error("[Client] unknown command. Use help to check the list of available commands")

                    else:
                        sys.exit(show_usage())

            # FIXME: testing command, not for production
            elif command in testing_commands:
                if command == 'generate_dummy_appointment':
                    generate_dummy_appointment()

            else:
                logging.error("[Client] unknown command. Use help to check the list of available commands")

        else:
            logging.error("[Client] no command provided. Use help to check the list of available commands.")

    except GetoptError as e:
        logging.error("[Client] {}".format(e))

    except json.JSONDecodeError as e:
        logging.error("[Client] non-JSON encoded appointment passed as parameter.")

