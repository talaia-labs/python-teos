def encode(value):
    """
    Encodes a value to BigSize.

    Args:
        value (:obj:`int`): the integer value to be encoded.

    Returns:
        :obj:`bytes`: the BigSize encoding of the given value.

    Raises:
        :obj:`TypeError`: If the provided value is not an integer.
        :obj:`ValueError`: If the provided value is negative or bigger than ``pow(2, 64)``.
    """

    if not isinstance(value, int):
        raise TypeError(f"value must be integer, {type(value)} received")

    if value < 0:
        raise ValueError(f"value must be a positive integer, {value} received")

    if value < pow(2, 8) - 3:
        return value.to_bytes(1, "big")
    elif value < pow(2, 16):
        return b"\xfd" + value.to_bytes(2, "big")
    elif value < pow(2, 32):
        return b"\xfe" + value.to_bytes(4, "big")
    elif value <= pow(2, 64):
        return b"\xff" + value.to_bytes(8, "big")
    else:
        raise ValueError("BigSize can only encode up to 8-byte values")


def decode(value):
    """
    Decodes a value fro BigSize.

    Args:
        value (:obj:`bytes`): the value to be decoded.

    Returns:
        :obj:`int`: the integer decoding of the provided value.
        
    Raises:
        :obj:`TypeError`: If the provided value is not in bytes.
        :obj:`ValueError`: If the provided value is bigger than 9-bytes or the value is not properly encoded.
    """

    if not isinstance(value, bytes):
        raise TypeError(f"value must be bytes, {type(value)} received")

    if len(value) > 9:
        raise ValueError(f"value must be, at most, 9-bytes long, {len(value)} received")

    if len(value) > 1:
        prefix = value[0]
        decoded_value = int.from_bytes(value[1:], "big")
    else:
        prefix = None
        decoded_value = int.from_bytes(value, "big")

    if not prefix and len(value) == 1 and decoded_value < pow(2, 8) - 3:
        return decoded_value
    elif prefix == 253 and len(value) == 3 and pow(2, 8) - 3 <= decoded_value < pow(2, 16):
        return decoded_value
    elif prefix == 254 and len(value) == 5 and pow(2, 16) <= decoded_value < pow(2, 32):
        return decoded_value
    elif prefix == 255 and len(value) == 9 and pow(2, 32) <= decoded_value:
        return decoded_value
    else:
        raise ValueError("value is not properly encoded")


def parse(value):
    """
    Parses a BigSize from a bytearray.

    Args:
        value (:obj:`bytes`): the bytearray from where the BigSize value will be parsed.

    Returns:
        :obj:`tuple`: A 2 items tuple containing the parsed BigSize and its encoded length (offset of the bytearray).

    Raises:
        :obj:`TypeError`: If the provided value is not in bytes.
        :obj:`ValueError`: If the provided value is not, at least, 1-byte long or if the value cannot be parsed.
    """

    if not isinstance(value, bytes):
        raise TypeError("value must be bytes")
    if len(value) < 1:
        raise ValueError("value must be at least 1-byte long")

    prefix = value[0]

    if prefix < 253:
        # prefix is actually the value to be parsed
        return decode(value[0:1]), 1
    else:
        if prefix == 253:
            return decode(value[0:3]), 3
        elif prefix == 254:
            return decode(value[0:5]), 5
        else:
            return decode(value[0:9]), 9
