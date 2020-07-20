import re
from pathlib import Path
from common.constants import LOCATOR_LEN_HEX


def is_compressed_pk(value):
    """
    Checks if a given value is a 33-byte hex-encoded string starting by 02 or 03.

    Args:
        value(:obj:`str`): the value to be checked.

    Returns:
        :obj:`bool`: Whether or not the value matches the format.
    """

    return isinstance(value, str) and re.match(r"^0[2-3][0-9A-Fa-f]{64}$", value) is not None


def is_256b_hex_str(value):
    """
    Checks if a given value is a 32-byte hex encoded string.

    Args:
        value(:mod:`str`): the value to be checked.

    Returns:
        :obj:`bool`: Whether or not the value matches the format.
    """
    return isinstance(value, str) and re.match(r"^[0-9A-Fa-f]{64}$", value) is not None


def is_u4int(value):
    """
    Checks if a given value is an unsigned 4-byte integer.

    Args:
        value(:mod:`int`): the value to be checked.

    Returns:
        :obj:`bool`: Whether or not the value matches the format.
    """
    return isinstance(value, int) and 0 <= value <= pow(2, 32) - 1


def is_locator(value):
    """
    Checks if a given value is a 16-byte hex encoded string.

    Args:
        value(:mod:`str`): the value to be checked.

    Returns:
        :obj:`bool`: Whether or not the value matches the format.
    """
    return isinstance(value, str) and re.match(r"^[0-9A-Fa-f]{32}$", value) is not None


def compute_locator(tx_id):
    """
    Computes an appointment locator given a transaction id.
    Args:
        tx_id (:obj:`str`): the transaction id used to compute the locator.
    Returns:
       :obj:`str`: The computed locator.
    """

    return tx_id[:LOCATOR_LEN_HEX]


def setup_data_folder(data_folder):
    """
    Create a data folder for either the client or the server side if the folder does not exists.

    Args:
        data_folder (:obj:`str`): the path of the folder.
    """

    Path(data_folder).mkdir(parents=True, exist_ok=True)
