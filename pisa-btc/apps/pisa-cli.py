from multiprocessing.connection import Client
from getopt import getopt
from sys import argv
from apps import PISA_API_SERVER, PISA_API_PORT
import apps.messages as msg
import re

commands = ['add_appointment']


def check_txid_format(txid):
    if len(txid) != 32:
        raise Exception("txid does not matches the expected size (16-byte / 32 hex chars). " + msg.wrong_txid)

    return re.search(r'^[0-9A-Fa-f]+$', txid) is not None


def show_usage():
    print("usage: python pisa-cli.py argument [additional_arguments]."
          "\nArguments:"
          "\nadd_appointment appointment: \tregisters a json formatted appointment "
          "\nhelp: \t\tshows this message.")


if __name__ == '__main__':
    opts, args = getopt(argv[1:], '', commands)

    # Get args
    if len(args) > 0:
        command = args[0]
    else:
        raise Exception("Argument missing. Use help for usage information.")

    if command in commands:

        if command in commands:
            if len(args) != 2:
                raise Exception("txid missing. " + msg.wrong_txid)

            arg = args[1]
            valid_locator = check_txid_format(arg)

            if valid_locator:
                conn = Client((PISA_API_SERVER, PISA_API_PORT))

                # Argv could be undefined, but we only have one command so it's safe for now
                conn.send((command, arg))
            else:
                raise ValueError("The provided locator is not valid. " + msg.wrong_txid)

    else:
        show_usage()

