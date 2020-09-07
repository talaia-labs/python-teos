import pytest
import common.net.bigsize as bigsize

# Test cases are copied from
# https://github.com/lightningnetwork/lightning-rfc/blob/bdd42711014643d5b2d4cbe179677451b940a9de/01-messaging.md

value_encoding_pair = {
    0: b"\x00",
    252: b"\xfc",
    253: b"\xfd\x00\xfd",
    65535: b"\xfd\xff\xff",
    65536: b"\xfe\x00\x01\x00\x00",
    4294967295: b"\xfe\xff\xff\xff\xff",
    4294967296: b"\xff\x00\x00\x00\x01\x00\x00\x00\x00",
    18446744073709551615: b"\xff\xff\xff\xff\xff\xff\xff\xff\xff",
}

non_canonical = [b"\xfd\x00\xfc", b"\xfe\x00\x00\xff\xff", b"\xff\x00\x00\x00\x00\xff\xff\xff\xff"]
unexpected_eof = [b"\xfd\x00", b"\xfe\xff\xff", b"\xff\xff\xff\xff\xff", b"", b"\xfd", b"\xfe", b"\xff"]

no_int = ["", 1.1, object(), b"\x00"]
no_bytes = ["", 1.1, object(), 0]


def test_encode():
    for k, v in value_encoding_pair.items():
        assert bigsize.encode(k) == v


def test_encode_wrong():
    # Wrong type
    for v in no_int:
        with pytest.raises(TypeError):
            bigsize.encode(v)

    # Negative value
    for i in range(-1, -100):
        with pytest.raises(ValueError, match="value must be a positive integer"):
            bigsize.encode(i)

    # Value bigger than 8-bytes
    with pytest.raises(ValueError, match="BigSize can only encode up to 8-byte values"):
        bigsize.encode(pow(2, 64) + 1)


def test_decode():
    for k, v in value_encoding_pair.items():
        assert bigsize.decode(v) == k


def test_decode_wrong():
    # Wrong type
    for v in no_bytes:
        with pytest.raises(TypeError):
            bigsize.decode(v)

    # Value too big (> 9-bytes)
    with pytest.raises(ValueError, match="value must be, at most, 9-bytes long"):
        bigsize.decode(bytes(10))

    # Wrong encoding
    for v in non_canonical:
        with pytest.raises(ValueError, match="Encoded BigSize is non-canonical"):
            bigsize.decode(v)

    for v in unexpected_eof:
        with pytest.raises(ValueError, match="Unexpected EOF while decoding BigSize"):
            bigsize.decode(v)


def test_parse():
    # Parsing should work for the properly encoded ones
    for k, v in value_encoding_pair.items():
        int_value, offset = bigsize.parse(v)
        assert int_value == k and offset == len(v)

    # Wrong encoding (behaves exactly like decode_wrong)
    for v in non_canonical:
        with pytest.raises(ValueError, match="Encoded BigSize is non-canonical"):
            bigsize.parse(v)


def test_parse_wrong():
    # Wrong type
    for v in no_bytes:
        with pytest.raises(TypeError):
            bigsize.parse(v)

    # Empty bytearray
    with pytest.raises(ValueError, match="value must be at least 1-byte long"):
        bigsize.parse(b"")

    # Value too big (> 9-bytes)
    with pytest.raises(ValueError, match="value must be, at most, 9-bytes long"):
        bigsize.decode(bytes(10))
