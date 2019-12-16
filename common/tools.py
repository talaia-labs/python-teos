import re


def check_sha256_hex_format(value):
    return isinstance(value, str) and re.match(r"^[0-9A-Fa-f]{64}$", value) is not None
