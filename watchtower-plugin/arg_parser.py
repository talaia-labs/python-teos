import re

from common.tools import is_compressed_pk, is_locator, is_256b_hex_str
from common.exceptions import InvalidParameter


def parse_register_arguments(args, default_port):
    # Sanity checks
    if len(args) == 0:
        raise InvalidParameter("missing required parameter: tower_id")

    if len(args) > 3:
        raise InvalidParameter("too many parameters: got {}, expected 3".format(len(args)))

    tower_id = args[0]

    if not isinstance(tower_id, str):
        raise InvalidParameter("tower id must be a compressed public key (33-byte hex value) " + str(args))

    # tower_id is of the form tower_id@[ip][:][port]
    if "@" in tower_id:
        if len(args) == 1:
            tower_id, tower_endpoint = tower_id.split("@")

            if not tower_endpoint:
                raise InvalidParameter("no tower endpoint was provided")

            # Only host was specified
            if ":" not in tower_endpoint:
                tower_endpoint = "{}:{}".format(tower_endpoint, default_port)

            # Colons where specified but no port, defaulting
            elif tower_endpoint.endswith(":"):
                tower_endpoint = "{}{}".format(tower_endpoint, default_port)

        else:
            raise InvalidParameter("cannot specify host as both xxx@yyy and separate arguments")

    # host was specified, but no port, defaulting
    elif len(args) == 2:
        tower_endpoint = "{}:{}".format(args[1], default_port)

    # host and port specified
    elif len(args) == 3:
        tower_endpoint = "{}:{}".format(args[1], args[2])

    else:
        raise InvalidParameter("tower host is missing")

    if not is_compressed_pk(tower_id):
        raise InvalidParameter("tower id must be a compressed public key (33-byte hex value)")

    return tower_id, tower_endpoint


def parse_get_appointment_arguments(args):
    # Sanity checks
    if len(args) == 0:
        raise InvalidParameter("missing required parameter: tower_id")

    if len(args) == 1:
        raise InvalidParameter("missing required parameter: locator")

    if len(args) > 2:
        raise InvalidParameter("too many parameters: got {}, expected 2".format(len(args)))

    tower_id = args[0]
    locator = args[1]

    if not is_compressed_pk(tower_id):
        raise InvalidParameter("tower id must be a compressed public key (33-byte hex value)")

    if not is_locator(locator):
        raise InvalidParameter("The provided locator is not valid", locator=locator)

    return tower_id, locator


def parse_add_appointment_arguments(kwargs):
    # Arguments to add_appointment come from c-lightning and they have been sanitised. Checking this just in case.
    commitment_txid = kwargs.get("commitment_txid")
    penalty_tx = kwargs.get("penalty_tx")

    if commitment_txid is None:
        raise InvalidParameter("missing required parameter: commitment_txid")

    if penalty_tx is None:
        raise InvalidParameter("missing required parameter: penalty_tx")

    if not is_256b_hex_str(commitment_txid):
        raise InvalidParameter("commitment_txid has invalid format")

    # Checking the basic stuff for the penalty transaction for now
    if type(penalty_tx) is not str or re.search(r"^[0-9A-Fa-f]+$", penalty_tx) is None:
        raise InvalidParameter("penalty_tx has invalid format")

    return commitment_txid, penalty_tx
