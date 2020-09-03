import pytest
import common.net.bigsize as bigsize
from common.net.utils import message_sanity_checks


def test_message_sanity_checks():
    # message_sanity_checks checks that:
    #   - A message is of the proper data type (bytes)
    #   - A message is at least ``min_len`` long
    #   - The message encoded type matches ``expected_type``:
    #       - If the message is a TLV the expected type is the first bigsize value of the message
    #       - Otherwise it is a u16.

    # Normal message
    min_len = 4
    expected_type = b"\x00\x01"
    message = 2 * expected_type
    assert message_sanity_checks(message, expected_type, min_len) is None

    # TLV (bigsize encoded)
    min_len = 3
    expected_type = bigsize.encode(1)
    message = expected_type + b"\x00\x01"
    assert message_sanity_checks(message, expected_type, min_len, tlv=True) is None


def test_message_sanity_checks_wrong_types():
    with pytest.raises(TypeError, match="message be must a bytearray"):
        message_sanity_checks("random_message", None, None)
    with pytest.raises(TypeError, match="expected_type be must bytes"):
        message_sanity_checks(b"", "random_type", None)
    with pytest.raises(TypeError, match="min_len be must int"):
        message_sanity_checks(b"", b"", 1.1)
    with pytest.raises(TypeError, match="tlv be must bool if set"):
        message_sanity_checks(b"", b"", 1, tlv=1.1)


def test_message_sanity_checks_wrong_data():
    # minimum size not met
    min_len = 3
    expected_type = b"\x01"
    message = expected_type + b"\x00"
    with pytest.raises(ValueError, match=f"message be must at least {min_len}-byte long"):
        message_sanity_checks(message, expected_type, min_len)

    # Wrong type (no TLV)
    min_len = 3
    expected_type = b"\x01"
    message = 3 * b"\x00"
    with pytest.raises(ValueError, match="Wrong message format. types do not match"):
        message_sanity_checks(message, expected_type, min_len)

    # Wrong type (TLV)
    min_len = 3
    expected_type = bigsize.encode(1)
    message = 3 * b"\x00"
    with pytest.raises(ValueError, match="Wrong message format. types do not match"):
        message_sanity_checks(message, expected_type, min_len, tlv=True)
