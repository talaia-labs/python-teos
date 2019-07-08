import requests
import re
import os
import json
from getopt import getopt, GetoptError
from sys import argv
import logging
from conf import CLIENT_LOG_FILE
from hashlib import sha256
from binascii import unhexlify
from apps.blob import Blob
from requests import ConnectTimeout
from apps import DEFAULT_PISA_API_SERVER, DEFAULT_PISA_API_PORT


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
        raise Exception("txid does not matches the expected size (32-byte / 64 hex chars).")

    return re.search(r'^[0-9A-Fa-f]+$', txid) is not None


def show_usage(show_and_quit=False):
    print("usage: python pisa-cli.py arguments [additional_arguments]."
          "\nArguments:"
          "\n-a, --add_appointment appointment: \tregisters a json formatted appointment"
          "\n-f, --file appointment_file: \tregisters an appointment from a an json formatted file"
          "\n-s, --server: \tAPI server where to send the requests. Defaults to localhost (modifiable in __init__.py)"
          "\n-p, --port: \tAPI port where to send the requests. Defaults to 9814 (modifiable in __init__.py)"
          "\n-d, --debug: \tshows debug information and stores it in pisa.log"
          "\n-h --help: \tshows this message.")

    if show_and_quit:
        exit(-1)


if __name__ == '__main__':
    debug = False
    help_command = False
    command = None
    appointment_data = None
    pisa_api_server = DEFAULT_PISA_API_SERVER
    pisa_api_port = DEFAULT_PISA_API_PORT
    commands = ['add_appointment']

    try:
        opts, args = getopt(argv[1:], 'a:-f:s:p:dh', ['add_appointment, file, server, port, debug, help'])

        for opt, arg in opts:
            if opt in ['-a', '--add_appointment']:
                if arg:
                    command = 'add_appointment'
                    appointment_data = json.loads(arg)
                else:
                    print("No appointment provided.")
                    show_usage(show_and_quit=True)

            elif opt in ['-f', '--file']:
                if arg:
                    if not os.path.isfile(arg):
                        print("Can't find file " + arg)
                        show_usage(show_and_quit=True)
                    else:
                        command = 'add_appointment'
                        appointment_data = json.load(open(arg))
                else:
                    raise Exception("Path to appointment_data.json missing.")
            if opt in ['-s', 'server']:
                if arg:
                    pisa_api_server = arg

            if opt in ['-p', '--port']:
                if arg:
                    pisa_api_port = int(arg)

            if opt in ['-d', '--debug']:
                debug = True

            if opt in ['-h', '--help']:
                help_command = True

    except GetoptError as e:
        print(e)
    except json.JSONDecodeError as e:
        print('Non-JSON encoded appointment passed as parameter.')

    # Configure logging
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO, handlers=[
        logging.FileHandler(CLIENT_LOG_FILE),
        logging.StreamHandler()
    ])

    if help_command:
        show_usage()
    elif command in commands:
        if command == 'add_appointment' and appointment_data:
            valid_locator = check_txid_format(appointment_data.get('tx_id'))

            if valid_locator:
                pisa_url = "http://{}:{}".format(pisa_api_server, pisa_api_port)
                appointment = build_appointment(appointment_data.get('tx'), appointment_data.get('tx_id'),
                                                appointment_data.get('start_time'), appointment_data.get('end_time'),
                                                appointment_data.get('dispute_delta'), debug, logging)

                if debug:
                    logging.info("[Client] sending appointment to PISA")

                try:
                    r = requests.post(url=pisa_url, json=json.dumps(appointment), timeout=5)

                    if debug:
                        logging.info("[Client] {} (code: {})".format(r.text, r.status_code))
                    else:
                        print("[Client] {} (code: {})".format(r.text, r.status_code))

                except ConnectTimeout:
                    if debug:
                        logging.info("[Client] can't connect to pisa API. Connection timeout")

            else:
                raise ValueError("The provided locator is not valid.")

    else:
        print("No valid appointment data provided.")
        show_usage(show_and_quit=True)

