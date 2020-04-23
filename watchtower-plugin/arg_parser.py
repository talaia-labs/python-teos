import re

from common.tools import is_compressed_pk, is_locator, is_256b_hex_str
from common.exceptions import InvalidParameter


def parse_register_arguments(tower_id, host, port, config):
    if not isinstance(tower_id, str):
        raise InvalidParameter(
            "tower id must be a compressed public key (33-byte hex value) not {}".format(str(tower_id))
        )

    # tower_id is of the form tower_id@[ip][:][port]
    if "@" in tower_id:
        if not (host and port):
            tower_id, tower_netaddr = tower_id.split("@")

            if not tower_netaddr:
                raise InvalidParameter("no tower endpoint was provided")

            # Only host was specified or colons where specified but not port
            if ":" not in tower_netaddr or tower_netaddr.endswith(":"):
                tower_netaddr = "{}:{}".format(tower_netaddr, config.get("DEFAULT_PORT"))

        else:
            raise InvalidParameter("cannot specify host as both xxx@yyy and separate arguments")

    # host was specified, but no port, defaulting
    elif host:
        tower_netaddr = "{}:{}".format(host, config.get("DEFAULT_PORT"))

    # host and port specified
    elif host and port:
        tower_netaddr = "{}:{}".format(host, port)

    else:
        raise InvalidParameter("tower host is missing")

    if not is_compressed_pk(tower_id):
        raise InvalidParameter("tower id must be a compressed public key (33-byte hex value)")

    return tower_id, tower_netaddr


def parse_get_appointment_arguments(tower_id, locator):
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
