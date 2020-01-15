import re
from common.constants import LOCATOR_LEN_HEX


def check_sha256_hex_format(value):
    """
    Checks if a given value is a 32-byte hex encoded string.

    Args:
        value(:mod:`str`): the value to be checked.

    Returns:
        :mod:`bool`: Whether or not the value matches the format.
    """
    return isinstance(value, str) and re.match(r"^[0-9A-Fa-f]{64}$", value) is not None


def compute_locator(tx_id):
    """
    Computes an appointment locator given a transaction id.
    Args:
        tx_id (:obj:`str`): the transaction id used to compute the locator.
    Returns:
       (:obj:`str`): The computed locator.
    """

    return tx_id[:LOCATOR_LEN_HEX]
