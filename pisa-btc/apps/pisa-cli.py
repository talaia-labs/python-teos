import requests
import re
import os
import json
from getopt import getopt
from sys import argv
import logging
from conf import CLIENT_LOG_FILE

from apps.blob import Blob
from apps import PISA_API_SERVER, PISA_API_PORT


commands = ['add_appointment']


def build_appointment(tx, tx_id, start_block, end_block, dispute_delta):
    locator = tx_id[:16]

    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    # FIXME: The blob data should contain more things that just the transaction. Leaving like this for now.
    blob = Blob(tx, cipher, hash_function)

    # FIXME: tx_id should not be necessary (can be derived from tx SegWit-like). Passing it for now
    encrypted_blob = blob.encrypt(tx_id)

    appointment = {"locator": locator, "start_block": start_block, "end_block": end_block,
                   "dispute_delta": dispute_delta, "encrypted_blob": encrypted_blob, "cipher": cipher, "hash_function":
                   hash_function}

    return appointment


def check_txid_format(txid):
    if len(txid) != 64:
        raise Exception("txid does not matches the expected size (32-byte / 64 hex chars).")

    return re.search(r'^[0-9A-Fa-f]+$', txid) is not None


def show_usage():
    print("usage: python pisa-cli.py argument [additional_arguments]."
          "\nArguments:"
          "\nadd_appointment appointment: \tregisters a json formatted appointment "
          "\nhelp: \t\tshows this message.")


if __name__ == '__main__':
    opts, args = getopt(argv[1:], '', commands)

    # Configure logging
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO, handlers=[
        logging.FileHandler(CLIENT_LOG_FILE),
        logging.StreamHandler()
    ])

    # Get args
    if len(args) > 0:
        command = args[0]
    else:
        raise Exception("Argument missing. Use help for usage information.")

    if command in commands:

        if command in commands:
            if len(args) != 2:
                raise Exception("Path to appointment_data.json missing.")

            if not os.path.isfile(args[1]):
                raise Exception("Can't find file " + args[1])

            appointment_data = json.load(open(args[1]))
            valid_locator = check_txid_format(appointment_data.get('tx_id'))

            if valid_locator:
                pisa_url = "http://{}:{}".format(PISA_API_SERVER, PISA_API_PORT)
                appointment = build_appointment(appointment_data.get('tx'), appointment_data.get('tx_id'),
                                                appointment_data.get('start_time'), appointment_data.get('end_time'),
                                                appointment_data.get('dispute_delta'))

                r = requests.post(url=pisa_url, json=json.dumps(appointment))

                logging.info("[Client] {} (code: {})".format(r.text, r.status_code))
            else:
                raise ValueError("The provided locator is not valid.")

    else:
        show_usage()

