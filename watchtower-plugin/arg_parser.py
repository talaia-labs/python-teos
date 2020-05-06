import re

from common.tools import is_compressed_pk, is_locator, is_256b_hex_str
from common.exceptions import InvalidParameter


def parse_register_arguments(tower_id, host, port, config):
    """
    Parses the arguments of the register command and checks that they are correct.

    Args:
        tower_id (:obj:`str`): the identifier of the tower to connect to (a compressed public key).
        host (:obj:`str`): the ip or hostname to connect to, optional.
        host (:obj:`int`): the port to connect to, optional.
        config: (:obj:`dict`): the configuration dictionary.

    Returns:
        :obj:`tuple`: the tower id and tower network address.

    Raises:
        :obj:`common.exceptions.InvalidParameter`: if any of the parameters is wrong or missing.
    """

    if not isinstance(tower_id, str):
        raise InvalidParameter(f"tower id must be a compressed public key (33-byte hex value) not {str(tower_id)}")

    # tower_id is of the form tower_id@[ip][:][port]
    if "@" in tower_id:
        if not (host and port):
            tower_id, tower_netaddr = tower_id.split("@")

            if not tower_netaddr:
                raise InvalidParameter("no tower endpoint was provided")

            # Only host was specified or colons where specified but not port
            if ":" not in tower_netaddr or tower_netaddr.endswith(":"):
                tower_netaddr = f"{tower_netaddr}:{config.get('DEFAULT_PORT')}"

        else:
            raise InvalidParameter("cannot specify host as both xxx@yyy and separate arguments")

    # host was specified, but no port, defaulting
    elif host:
        tower_netaddr = f"{host}:{config.get('DEFAULT_PORT')}"

    # host and port specified
    elif host and port:
        tower_netaddr = f"{host}:{port}"

    else:
        raise InvalidParameter("tower host is missing")

    if not is_compressed_pk(tower_id):
        raise InvalidParameter("tower id must be a compressed public key (33-byte hex value)")

    return tower_id, tower_netaddr


def parse_get_appointment_arguments(tower_id, locator):
    """
    Parses the arguments of the get_appointment command and checks that they are correct.

    Args:
        tower_id (:obj:`str`): the identifier of the tower to connect to (a compressed public key).
        locator (:obj:`str`): the locator of the appointment to query the tower about.

    Returns:
        :obj:`tuple`: the tower id and appointment locator.

    Raises:
        :obj:`common.exceptions.InvalidParameter`: if any of the parameters is wrong or missing.
    """

    if not is_compressed_pk(tower_id):
        raise InvalidParameter("tower id must be a compressed public key (33-byte hex value)")

    if not is_locator(locator):
        raise InvalidParameter("The provided locator is not valid", locator=locator)

    return tower_id, locator


def parse_add_appointment_arguments(kwargs):
    """
    Parses the arguments of the add_appointment command and checks that they are correct.

    The expected arguments are a commitment transaction id (32-byte hex string) and the penalty transaction.

    Args:
        kwargs (:obj:`dict`): a dictionary of arguments.

    Returns:
        :obj:`tuple`: the commitment transaction id and the penalty transaction.

    Raises:
        :obj:`common.exceptions.InvalidParameter`: if any of the parameters is wrong or missing.
    """

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
