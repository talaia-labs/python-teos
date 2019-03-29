from multiprocessing.connection import Client
from getopt import getopt
from sys import argv
from apps import PISA_API_SERVER, PISA_API_PORT
import apps.messages as msg
from base58 import b58decode


commands = ['register_tx']


def check_txid_format(txid):
    if len(txid) != 32:
        raise Exception("txid does not matches the expected size (16-byte / 32 hex chars). " + msg.wrong_txid)
    try:
        b58decode(txid)
    except ValueError:
        raise Exception("The provided txid is not in base58. " + msg.wrong_txid)


def show_usage():
    print("usage: python pisa-cli.py argument [additional_arguments]."
          "\nArguments:"
          "\nregister_tx half_txid: \tregisters a txid to be monitored by PISA using the 16 MSB of the txid (in hex)."
          "\nhelp: \t\tshows this message.")


if __name__ == '__main__':
    opts, args = getopt(argv[1:], '', commands)

    # Get args
    if len(args) > 0:
        command = args[0]
    else:
        raise Exception("Argument missing. Use help for usage information.")

    if command in commands:

        if command == 'register_tx':
            if len(args) != 2:
                raise Exception("txid missing. " + msg.wrong_txid)

            arg = args[1]
            check_txid_format(arg)

        conn = Client((PISA_API_SERVER, PISA_API_PORT))

        # Argv could be undefined, but we only have one command for now so safe
        conn.send((command, arg))

    else:
        show_usage()

