import pytest

import common.net.bigsize as bigsize
from common.net.tlv import TLVRecord, NetworksTLV

from test.common.unit.conftest import get_random_value_hex


def test_tlv_record():
    # The TLV record only enforces the fields to be bytes
    tlv = TLVRecord(b"\x01", b"\x02", b"\x03")
    assert tlv.type == b"\x01" and tlv.length == b"\x02" and tlv.value == b"\x03"

    # If any of the fields is not byte it'll fail
    with pytest.raises(TypeError, match="t must be bytes"):
        TLVRecord("", b"\x02", b"\x03")
    with pytest.raises(TypeError, match="l must be bytes"):
        TLVRecord(b"\x01", "", b"\x03")
    with pytest.raises(TypeError, match="v must be bytes"):
        TLVRecord(b"\x01", b"\x02", "")


def test_tlv_record_len():
    # The TLV length is defined as the length of its serialized fields
    t = b"\x01"
    l = b"\x02"
    v = b"\x03"
    tlv = TLVRecord(t, l, v)
    assert len(tlv) == len(t) + len(l) + len(v)


def test_tlv_record_from_bytes():
    # from_bytes builds an instance of a child class depending on the data type. Currently it only supports Networks.

    # NetworksTLV
    t = bigsize.encode(1)
    l = bigsize.encode(32)
    v = bytes.fromhex(get_random_value_hex(32))
    ntlv = TLVRecord.from_bytes(t + l + v)

    assert isinstance(ntlv, NetworksTLV)
    assert ntlv.type == t and ntlv.length == l and ntlv.value == v

    # Any other (unknown types) will return TLVRecord
    t = bigsize.encode(0)
    tlv = TLVRecord.from_bytes(t + l + v)
    assert isinstance(ntlv, TLVRecord)
    assert tlv.type == t and tlv.length == l and tlv.value == v


# Test cases are copied from
# https://github.com/lightningnetwork/lightning-rfc/blob/bdd42711014643d5b2d4cbe179677451b940a9de/01-messaging.md
def test_tlv_record_from_bytes_failures():
    # We do not count unknown even types since we are only decoding here
    unexpected_eof = [
        b"\xfd",
        b"\xfd\x01",
        b"\xfd\x00\x01\x00",
        b"\xfd\x01\x01",
        b"\x0f\xfd",
        b"\x0f\xfd\x26",
        b"\x0f\xfd\x26\x02",
        b"\x0f\xfd\x00\x01\x00",
        b"\x0f\xfd\x02\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00",
    ]

    for v in unexpected_eof:
        with pytest.raises(ValueError, match="Wrong tlv message format. Unexpected EOF"):
            TLVRecord.from_bytes(v)


def test_tlv_record_from_bytes_wrong_types():
    # If the provided message is not in bytes, from_bytes will fail
    with pytest.raises(TypeError, match="message must be bytes"):
        TLVRecord.from_bytes("random_message")


def test_networks_tlv():
    # Networks TLV expects a list of genesis block hashes (32-byte hex str elements) or an empty list, if no network
    # is supported

    # Empty can be achieved with an empty list or no networks at all
    empty_ntlv = NetworksTLV()
    empty_ntlv2 = NetworksTLV(networks=[])
    assert empty_ntlv.networks == empty_ntlv2.networks == []
    assert empty_ntlv.type == empty_ntlv2.type == b"\x01"
    assert empty_ntlv.length == empty_ntlv2.length == b"\x00"
    assert empty_ntlv.value == empty_ntlv2.value == b""

    random_networks = [get_random_value_hex(32) for _ in range(10)]
    random_network_bytearray = b"".join(bytes.fromhex(network) for network in random_networks)
    ntlv_random = NetworksTLV(random_networks)
    assert ntlv_random.type == b"\x01"
    assert ntlv_random.length == bigsize.encode(32 * 10)
    assert ntlv_random.value == random_network_bytearray
    assert ntlv_random.networks == random_networks


def test_networks_tlv_wrong_data():
    # If networks is not a list we'll get an error
    with pytest.raises(TypeError, match="networks must be a list if set"):
        NetworksTLV(1)

    # If the list does not contain only 32-byte hex encoded values, it will fail
    wrong_lists = [[1, 2, 3], [""], [get_random_value_hex(32), get_random_value_hex(31)]]
    for networks in wrong_lists:
        with pytest.raises(ValueError, match="All networks must be 32-byte hex str"):
            NetworksTLV(networks)


def test_networks_tlv_from_bytes():
    # from_bytes from NetworksTLV expects the type to match (01) and the data a collection of 32-byte hashes (if set)
    t = bigsize.encode(1)
    l = bigsize.encode(128)
    v = b"".join(bytes.fromhex(get_random_value_hex(32)) for _ in range(4))
    ntlv = NetworksTLV.from_bytes(t + l + v)
    assert ntlv.type == t and ntlv.length == l and ntlv.value == v

    # Works for empty too
    empty_l = b"\x00"
    empty_ntlv = NetworksTLV.from_bytes(t + empty_l)
    assert empty_ntlv.type == t and empty_ntlv.length == empty_l and empty_ntlv.value == b""


def test_networks_tlv_from_bytes_wrong():
    # message must be bytes
    with pytest.raises(TypeError, match="message be must a bytearray"):
        NetworksTLV.from_bytes("random_message")

    # If the type is not networks, it will fail
    with pytest.raises(ValueError, match="Wrong message format. types do not match"):
        l = bigsize.encode(128)
        v = bytes.fromhex(get_random_value_hex(32))
        NetworksTLV.from_bytes(b"\x00" + l + v)

    # Data must be multiple of 32
    # Encoding 128, data_len = 127
    with pytest.raises(ValueError, match="All networks must be 32-byte hex str"):
        t = b"\x01"
        l = bigsize.encode(128)
        v = bytes.fromhex(get_random_value_hex(32))
        NetworksTLV.from_bytes(t + l + v[:-1])

    #  Encoding 127, data_len = 127
    with pytest.raises(ValueError, match="chains must be multiple of 32"):
        t = b"\x01"
        l = bigsize.encode(127)
        v = bytes.fromhex(get_random_value_hex(32))
        NetworksTLV.from_bytes(t + l + v[:-1])
