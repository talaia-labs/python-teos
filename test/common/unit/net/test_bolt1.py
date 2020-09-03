import pytest

from common.net.bolt1 import Message, InitMessage, ErrorMessage, PingMessage, PongMessage
from common.net.bolt9 import FeatureVector
from common.net.tlv import TLVRecord, NetworksTLV

from test.common.unit.conftest import get_random_value_hex


def test_message():
    # Messages are built from a message_type (bytes) a payload (bytes) an a optional list of TLVRecords
    mtype = b"\x00"
    payload = b"\x00\x01\x02"
    extension = []
    m = Message(mtype, payload, extension)
    assert isinstance(m, Message)
    assert m.type == mtype and m.payload == payload and m.extension is None

    # Same with some tlvs
    extension = [TLVRecord(), NetworksTLV()]
    m2 = Message(mtype, payload, extension)
    assert isinstance(m2, Message)
    assert m2.type == mtype and m2.payload == payload and m2.extension == extension


def test_message_wrong_types():
    # Wrong mtype
    with pytest.raises(TypeError, match="mtype must be bytes"):
        Message("", b"")

    # Wrong payload
    with pytest.raises(TypeError, match="payload must be bytes"):
        Message(b"", "")

    # Wrong extension type
    with pytest.raises(TypeError, match="extension must be a list if set"):
        Message(b"", b"", "")

    # Wrong extension content
    with pytest.raises(TypeError, match="All items in extension must be TLVRecords"):
        Message(b"", b"", [TLVRecord(), 1])


def test_message_from_bytes():
    # From bytes builds an instance of a children class as long as the type is known, raises ValueError otherwise
    # Not testing particular cases for the children since they will be covered in their own tests

    # Init
    m = b"\x00\x10\x00\x00\x00\x00"
    assert isinstance(Message.from_bytes(m), InitMessage)

    # Error
    m = b"\x00\x11" + bytes.fromhex(get_random_value_hex(32)) + b"\x00\x00"
    assert isinstance(Message.from_bytes(m), ErrorMessage)

    # Ping
    m = b"\x00\x12\x00\x00\x00\x00"
    assert isinstance(Message.from_bytes(m), PingMessage)

    # Pong
    m = b"\x00\x13\x00\x00"
    assert isinstance(Message.from_bytes(m), PongMessage)

    # Unknown
    with pytest.raises(ValueError, match="Cannot decode unknown message type"):
        Message.from_bytes(b"\x00\xff")


def test_message_from_bytes_wrong():
    # Message must be bytes
    with pytest.raises(TypeError, match="message be must a bytearray"):
        Message.from_bytes("random_message")

    # Message must be at least 2-byte long to account for the type
    with pytest.raises(ValueError, match="message be must at least 2-byte long"):
        Message.from_bytes(b"\x00")


def test_message_serialize():
    # Serialize returns the concatenation opf the byte representation of each field:
    # type + payload + [extension]

    # No extension
    mtype = b"\x00\x001"
    payload = b"\x00\x00\x00\x00"
    assert Message(mtype, payload).serialize() == mtype + payload

    # With extensions
    extension = [TLVRecord(t=b"\x00", l=b"\x01", v=b"\x02")]
    assert Message(mtype, payload, extension).serialize() == mtype + payload + b"\x00" + b"\x01" + b"\x02"


def test_init_message():
    # Init message requires global_features(FeatureVector), local_features (FeatureVector) and optionally a NetworksTLV
    gf = FeatureVector.from_bytes(b"\x02")
    lf = FeatureVector()
    im = InitMessage(gf, lf)
    assert isinstance(im, InitMessage)
    assert im.global_features == gf and im.local_features == lf and im.networks is None

    # Same with networks
    networks = NetworksTLV([get_random_value_hex(32) for _ in range(5)])
    im2 = InitMessage(gf, lf, networks)
    assert isinstance(im2, InitMessage)
    assert im2.global_features == gf and im2.local_features == lf and im2.networks is networks


def test_init_message_wrong():
    # No FeatureVectors
    with pytest.raises(TypeError, match="global_features and local_features must be FeatureVector instances"):
        InitMessage("features", FeatureVector())
    with pytest.raises(TypeError, match="global_features and local_features must be FeatureVector instances"):
        InitMessage(FeatureVector(), "features")

    # TLV must be NetworksTLV is fet (for now)
    with pytest.raises(TypeError, match="networks must be of type NetworksTLV"):
        InitMessage(FeatureVector(), FeatureVector(), "TLV")


def test_init_message_from_bytes():
    # Message type must be init and size at least 6 (type + gflen + flen)
    mtype = b"\x00\x10"
    gflen = b"\x00\x00"
    flen = gflen
    im = InitMessage.from_bytes(mtype + gflen + flen)
    assert (
        isinstance(im, InitMessage)
        and im.type == mtype
        and im.global_features.serialize() == im.local_features.serialize() == b""
    )

    # A more meaningful init (with some features)
    mtype = b"\x00\x10"
    global_features = b"\x2a\xaa\xaa"  # All odd
    gflen = b"\x00\x03"
    local_features = b"\x01"  # Feature 1 even
    flen = b"\x00\x01"
    im2 = InitMessage.from_bytes(mtype + gflen + global_features + flen + local_features)
    assert (
        isinstance(im2, InitMessage)
        and im2.type == mtype
        and im2.global_features.serialize() == global_features
        and im2.local_features.serialize() == local_features
    )

    # With some networks
    networks = NetworksTLV([get_random_value_hex(32) for _ in range(5)])
    im3 = InitMessage.from_bytes(mtype + gflen + global_features + flen + local_features + networks.serialize())
    assert (
        isinstance(im3, InitMessage)
        and im3.type == mtype
        and im3.global_features.serialize() == global_features
        and im3.local_features.serialize() == local_features
        and im3.networks == networks
    )


def test_init_message_from_bytes_wrong():
    # Message is not bytes
    with pytest.raises(TypeError, match="message be must a bytearray"):
        InitMessage.from_bytes("message")

    # Message is not long enough < 6
    with pytest.raises(ValueError, match="message be must at least 6-byte long"):
        InitMessage.from_bytes(b"\x00\x10\x00")

    # Type is not init
    with pytest.raises(ValueError, match="Wrong message format. types do not match"):
        InitMessage.from_bytes(b"\x00\x00\x00\x00\x00\x00")

    # Encoded lengths are wrong causing an unexpected EOF
    with pytest.raises(ValueError, match="Wrong message format. Unexpected EOF"):
        InitMessage.from_bytes(b"\x00\x10\x00\x01\x00\x00")


def test_error_message():
    # Error message expects a channel_id (32-hex encoded str) and an optional data field
    cid = get_random_value_hex(32)
    em = ErrorMessage(cid)
    assert isinstance(em, ErrorMessage)
    assert em.channel_id == cid
    assert em.data is None

    # Same with associated data
    data = "error message data"
    em2 = ErrorMessage(cid, data)
    assert isinstance(em, ErrorMessage)
    assert em2.channel_id == cid
    assert em2.data == data


def test_error_message_wrong():
    # Channel id must be a 32-byte hex str
    # Data must be string if set and no longer than the message cap size when encoded pow(2, 16)

    # Wrong channel id
    with pytest.raises(ValueError, match="channel_id must be a 256-bit hex string"):
        ErrorMessage(get_random_value_hex(31))

    with pytest.raises(ValueError, match="channel_id must be a 256-bit hex string"):
        ErrorMessage(dict())

    # Wrong data type
    with pytest.raises(ValueError, match="data must be string if set"):
        ErrorMessage(get_random_value_hex(32), b"message")

    # Data too long
    with pytest.raises(ValueError, match=f"Encoded data length cannot be bigger than {pow(2, 16)}"):
        ErrorMessage(get_random_value_hex(32), "A" * (pow(2, 16) + 1))


def test_error_from_bytes():
    # Message must be, at least, 36-bytes long
    mtype = b"\x00\x11"
    cid = bytes.fromhex(get_random_value_hex(32))
    data_len = b"\x00\x00"

    em = ErrorMessage.from_bytes(mtype + cid + data_len)
    assert isinstance(em, ErrorMessage)
    assert em.channel_id == cid.hex()
    assert em.data is None

    # Same with associated data
    data = "message"
    data_len = len(data).to_bytes(2, "big")
    em2 = ErrorMessage.from_bytes(mtype + cid + data_len + data.encode("utf-8"))
    assert isinstance(em2, ErrorMessage)
    assert em2.channel_id == cid.hex()
    assert em2.data == data


def test_error_from_bytes_wrong():
    # Message is not bytes
    with pytest.raises(TypeError, match="message be must a bytearray"):
        ErrorMessage.from_bytes("message")

    # Message is not long enough < 36
    with pytest.raises(ValueError, match="message be must at least 36-byte long"):
        ErrorMessage.from_bytes(b"\x00\x11\x00\x01")

    # Type is not error
    with pytest.raises(ValueError, match="Wrong message format. types do not match"):
        ErrorMessage.from_bytes(b"\x00\x10" + bytes.fromhex(get_random_value_hex(32)) + b"\x00\x00")

    # Encoded lengths are wrong causing an unexpected EOF
    with pytest.raises(ValueError, match="Wrong message format. Unexpected EOF"):
        ErrorMessage.from_bytes(b"\x00\x11" + bytes.fromhex(get_random_value_hex(32)) + b"\x00\x02\x00")

    # Encoded lengths are wrong leaving additional data at the end
    with pytest.raises(ValueError, match="Wrong data format. message has additional tailing data"):
        ErrorMessage.from_bytes(b"\x00\x11" + bytes.fromhex(get_random_value_hex(32)) + b"\x00\x01\x00\x00")


def test_ping_message():
    # Ping expects a number of pong bytes and optionally a some ignored data (bytes)
    num_pong_bytes = 10
    pm = PingMessage(num_pong_bytes)
    assert isinstance(pm, PingMessage)
    assert pm.num_pong_bytes == num_pong_bytes

    # Same with ignore_bytes
    ignored_bytes = b"\x01\x04\xff\x00"
    pm2 = PingMessage(num_pong_bytes, ignored_bytes)
    assert isinstance(pm2, PingMessage)
    assert pm2.num_pong_bytes == num_pong_bytes
    assert pm2.ignored_bytes == ignored_bytes


def test_ping_message_wrong():
    # num_pong_bytes must be an integer between 0 and pow(2, 16)
    with pytest.raises(ValueError, match=f"num_pong_bytes must be between 0 and {pow(2, 16)}"):
        PingMessage(-1)
    with pytest.raises(ValueError, match=f"num_pong_bytes must be between 0 and {pow(2, 16)}"):
        PingMessage(pow(2, 16))

    # ignore_bytes must be bytes if set
    with pytest.raises(TypeError, match="ignored_bytes must be bytes if set"):
        PingMessage(pow(2, 16) - 1, "ignored_bytes")

    # ignore_bytes length cannot be bigger than pow(2, 16) - 4
    with pytest.raises(ValueError, match=f"ignored_bytes cannot be higher than {pow(2, 16) - 4}"):
        PingMessage(10, bytes(pow(2, 16) - 3))


def test_ping_message_from_bytes():
    # message must be at least 6 bytes long (type + num_pong_bytes + byteslen)
    mtype = b"\x00\x12"
    num_pong_bytes = b"\x00\x01"
    bytes_len = b"\x00\x00"

    pm = PingMessage.from_bytes(mtype + num_pong_bytes + bytes_len)
    assert isinstance(pm, PingMessage)
    assert pm.num_pong_bytes == int.from_bytes(num_pong_bytes, "big")
    assert pm.ignored_bytes is None

    # Same with some ignored data
    ignored_data = b"\x00\x01\x02\x03"
    bytes_len = b"\x00\x04"
    pm2 = PingMessage.from_bytes(mtype + num_pong_bytes + bytes_len + ignored_data)
    assert isinstance(pm2, PingMessage)
    assert pm2.num_pong_bytes == int.from_bytes(num_pong_bytes, "big")
    assert pm2.ignored_bytes == ignored_data


def test_ping_message_from_bytes_wrong():
    # Message is not bytes
    with pytest.raises(TypeError, match="message be must a bytearray"):
        PingMessage.from_bytes("message")

    # Message is not long enough < 6
    with pytest.raises(ValueError, match="message be must at least 6-byte long"):
        PingMessage.from_bytes(b"\x00\x12\x00\x01")

    # Type is not ping
    with pytest.raises(ValueError, match="Wrong message format. types do not match"):
        PingMessage.from_bytes(b"\x00\x10\x00\x01\x00\x00")

    # Encoded lengths are wrong causing an unexpected EOF
    with pytest.raises(ValueError, match="Wrong message format. Unexpected EOF"):
        PingMessage.from_bytes(b"\x00\x12\x00\x00\x00\x01")

    # Encoded lengths are wrong leaving additional data at the end
    with pytest.raises(ValueError, match="Wrong data format. message has additional tailing data"):
        PingMessage.from_bytes(b"\x00\x12\x00\x00\x00\x01\x00\x00")


def test_pong_message():
    # Pong can be empty, and optionally can receive so ignored bytes
    pm = PongMessage()
    assert isinstance(pm, PongMessage)
    assert pm.ignored_bytes is None

    # With some ignored_bytes
    ignored_bytes = b"\x00\x02\x06"
    pm2 = PongMessage(ignored_bytes)
    assert isinstance(pm2, PongMessage)
    assert pm2.ignored_bytes is ignored_bytes


def test_pong_message_wrong():
    # ignored_bytes must be bytes if set
    with pytest.raises(TypeError, match="ignored_bytes must be bytes if set"):
        PongMessage("ignored_bytes")

    # ignore_bytes length cannot be bigger than pow(2, 16) - 4
    with pytest.raises(ValueError, match=f"ignored_bytes cannot be higher than {pow(2, 16) - 4}"):
        PongMessage(bytes(pow(2, 16) - 3))


def test_pong_message_from_bytes():
    # message must be bytes and length at least 4 (mtype + byteslen)
    mtype = b"\x00\x13"
    bytes_len = b"\x00\x00"
    pm = PongMessage.from_bytes(mtype + bytes_len)
    assert isinstance(pm, PongMessage)
    assert pm.ignored_bytes is None

    # Add some ignored data
    ignored_data = b"\x03\xfd\xef"
    data_len = b"\x00\x03"
    pm2 = PongMessage.from_bytes(mtype + data_len + ignored_data)
    assert isinstance(pm2, PongMessage)
    assert pm2.ignored_bytes == ignored_data


def test_pong_message_from_bytes_wrong():
    # Message is not bytes
    with pytest.raises(TypeError, match="message be must a bytearray"):
        PongMessage.from_bytes("message")

    # Message is not long enough < 4
    with pytest.raises(ValueError, match="message be must at least 4-byte long"):
        PongMessage.from_bytes(b"\x00\x13\x00")

    # Type is not pong
    with pytest.raises(ValueError, match="Wrong message format. types do not match"):
        PongMessage.from_bytes(b"\x00\x10\x00\x00")

    # Encoded lengths are wrong causing an unexpected EOF
    with pytest.raises(ValueError, match="Wrong message format. Unexpected EOF"):
        PongMessage.from_bytes(b"\x00\x13\x00\x01")

    # Encoded lengths are wrong leaving additional data at the end
    with pytest.raises(ValueError, match="Wrong data format. message has additional tailing data"):
        PongMessage.from_bytes(b"\x00\x13\x00\x01\x00\x01")
