import re


def check_sha256_hex_format(value):
    """
    Checks if a given value is a 32-byte hex encoded string.

    Args:
        value(:mod:`str`): the value to be checked.

    Returns:
        :mod:`bool`: Wether or not the value matches the format.
    """
    return isinstance(value, str) and re.search(r"^[0-9A-Fa-f]{64}$", value) is not None
