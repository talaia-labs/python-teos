import common.net.bigsize as bigsize


def message_sanity_checks(message, expected_type, min_len, tlv=False):
    """
    Runs sanity checks to a received byte-encoded message, such as checking its minimum length or message type.

    Args:
        message (:obj:`bytes`): the bytes-encoded message.
        expected_type (:obj:`str`): the expected type of the message.
        min_len (:obj:`int`): the minimum expected length of the message.
        tlv (:obj:`bool`): whether the message is a tlv record or not.

    Raises:
        :obj:`TypeError`: If the provided message is not in bytes.
        :obj:`ValueError`: If the provided message is not long enough or not of the expected type.
    """

    if not isinstance(message, bytes):
        raise TypeError("message be must a bytearray")
    if not isinstance(expected_type, bytes):
        raise TypeError("expected_type be must bytes")
    if not isinstance(min_len, int):
        raise TypeError("min_len be must int")
    if not isinstance(tlv, bool):
        raise TypeError("tlv be must bool if set")
    if len(message) < min_len:
        raise ValueError(f"message be must at least {min_len}-byte long")

    if tlv:
        tlv_type, type_length = bigsize.parse(message)
        tlv_type_byte = tlv_type.to_bytes(type_length, "big")
        if tlv_type_byte != expected_type:
            raise ValueError(
                f"Wrong message format. types do not match (expected: {expected_type}, received: {tlv_type_byte}"
            )
    else:
        if message[:2] != expected_type:
            raise ValueError(
                f"Wrong message format. types do not match (expected: {expected_type}, received: {message[:2]}"
            )
