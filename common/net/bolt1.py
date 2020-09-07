from common.tools import is_256b_hex_str

from common.net.tlv import TLVRecord, NetworksTLV
from common.net.bolt9 import FeatureVector
from common.net.utils import message_sanity_checks


message_types = {"init": b"\x00\x10", "error": b"\x00\x11", "ping": b"\x00\x12", "pong": b"\x00\x13"}


class Message:
    """
    Message class. Used as a base class for all other messages.

    Args:
        mtype (:obj:`bytes`): the message type.
        payload (:obj:`bytes`): the message payload.
        extension (:obj:`bytes`): the message extension, if any (optional).

    Attributes:
        type (:obj:`bytes`): the message type.
        payload (:obj:`bytes`): the message payload.
        extension (:obj:`bytes`): the message extension, if any (optional).
    """

    def __init__(self, mtype, payload, extension=None):
        if not isinstance(mtype, bytes):
            raise TypeError("mtype must be bytes")
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if extension is not None and not isinstance(extension, list):
            raise TypeError("extension must be a list if set")
        else:
            # Normalize the default extension type (for empty lists)
            if not extension:
                extension = None
            elif not all(isinstance(tlv, TLVRecord) for tlv in extension):
                raise TypeError("All items in extension must be TLVRecords")

        self.type = mtype
        self.payload = payload
        self.extension = extension

    @classmethod
    def from_bytes(cls, message):
        """
        Builds a message from its byte representation.

        Args:
            message (:obj:`bytes`): the byte-encoded message.

        Returns:
            The Message children class depending on the received message type. Check ``message_types`` for more info.

        Raises:
            :obj:`TypeError`: If the given message is not in bytes.
            :obj:`ValueError`: If the message can not be parsed.
        """

        if not isinstance(message, bytes):
            raise TypeError("message be must a bytearray")
        if len(message) < 2:
            raise ValueError("message be must at least 2-byte long")

        mtype = message[:2]

        if mtype == message_types["init"]:
            return InitMessage.from_bytes(message)
        elif mtype == message_types["error"]:
            return ErrorMessage.from_bytes(message)
        elif mtype == message_types["ping"]:
            return PingMessage.from_bytes(message)
        elif mtype == message_types["pong"]:
            return PongMessage.from_bytes(message)
        else:
            raise ValueError("Cannot decode unknown message type")

    def serialize(self):
        """Serializes the message."""
        if not self.extension:
            return self.type + self.payload
        else:
            tlvs = b"".join([tlv.serialize() for tlv in self.extension])
            return self.type + self.payload + tlvs


class InitMessage(Message):
    """
    First message exchange by the nodes, it reveals the features supported by each end.

    Args:
        global_features (:obj:`FeatureVector <teos.net.bolt9.FeatureVector>`): the global features vector.
        local_features (:obj:`FeatureVector <teos.net.bolt9.FeatureVector>`): the local features vector.
        networks (:obj:`NetworksTLV <common.net.tlv.NetworksTLV>`): a networks tlv (optional).
    """

    def __init__(self, global_features, local_features, networks=None):
        if not (isinstance(global_features, FeatureVector) and isinstance(local_features, FeatureVector)):
            raise TypeError("global_features and local_features must be FeatureVector instances")
        if networks:
            if not isinstance(networks, NetworksTLV):
                raise TypeError("networks must be of type NetworksTLV (if set)")

        gf = global_features.serialize()
        lf = local_features.serialize()
        gflen = len(gf).to_bytes(2, "big")
        flen = len(lf).to_bytes(2, "big")
        payload = gflen + gf + flen + lf

        # Add extensions if needed (this follows TLV format)
        # FIXME: Only networks for now
        if networks:
            super().__init__(mtype=message_types["init"], payload=payload, extension=[networks])
        else:
            super().__init__(mtype=message_types["init"], payload=payload)
        self.global_features = global_features
        self.local_features = local_features
        self.networks = networks

    @classmethod
    def from_bytes(cls, message):
        """Builds an InitMessage from its byte representation."""
        # Message should be at least: type (2-byte) + gflen (2-byte) + flen (2 byte)
        message_sanity_checks(message, message_types["init"], 6)

        try:
            gflen = int.from_bytes(message[2:4], "big")
            global_features = FeatureVector.from_bytes(message[4 : gflen + 4])
            flen = int.from_bytes(message[gflen + 4 : gflen + 6], "big")
            local_features = FeatureVector.from_bytes(message[gflen + 6 : gflen + flen + 6])
            if gflen + flen + 6 > len(message):
                raise ValueError()  # Unexpected EOF

            # Check if there are TLVs (optional)
            if len(message) > gflen + flen + 6:
                # FIXME: Only accepting networks TLV for now
                networks = NetworksTLV.from_bytes(message[gflen + flen + 6 :])
                return cls(global_features, local_features, networks)

            return cls(global_features, local_features)

        except ValueError:
            raise ValueError("Wrong message format. Unexpected EOF")


class ErrorMessage(Message):
    """
    Message for error reporting.

    Args:
        channel_id (:obj:`str`): a 32-byte long hex str identifying the channel that originated the error, or 0 if it
            refers to all channels.
        data (:obj:`str`): the error message.
    """

    def __init__(self, channel_id, data=None):
        if not is_256b_hex_str(channel_id):
            raise ValueError("channel_id must be a 256-bit hex string")

        payload = bytes.fromhex(channel_id)

        if data:
            if not isinstance(data, str):
                raise ValueError("data must be string if set")

            encoded_message = data.encode("utf-8")
            if len(encoded_message) > pow(2, 16):
                raise ValueError(
                    f"Encoded data length cannot be bigger than {pow(2, 16)}, {len(encoded_message)} received"
                )

            payload += len(encoded_message).to_bytes(2, "big") + encoded_message

        super().__init__(message_types["error"], payload)
        self.channel_id = channel_id
        self.data = data

    @classmethod
    def from_bytes(cls, message):
        """Builds an ErrorMessage from its byte representation."""
        # Message should be at least: type (2-byte) + channel_id (32-byte) + data_len (2-bytes)
        message_sanity_checks(message, message_types["error"], 36)
        channel_id = message[2:34].hex()
        data_len = int.from_bytes(message[34:36], "big")

        # There's associated data
        if data_len:
            data = message[36 : 36 + data_len]

            if len(data) < data_len:
                raise ValueError("Wrong message format. Unexpected EOF")
            if len(message) > 36 + data_len:
                raise ValueError("Wrong data format. message has additional trailing data")
            return cls(channel_id, data.decode("utf-8"))

        return cls(channel_id)


class PingMessage(Message):
    """
    Message to test the reachability of the other side of the channel. Useful to allow long lived communications.

    Args:
        num_pong_bytes (:obj:`int`): the number of bytes to be responded by the peer.
        ignored_bytes (:obj:`bytes`): filling bytes added to the message by the sender.
    """

    def __init__(self, num_pong_bytes, ignored_bytes=None):
        if not 0 <= num_pong_bytes < pow(2, 16):
            raise ValueError(f"num_pong_bytes must be between 0 and {pow(2, 16)}")

        payload = num_pong_bytes.to_bytes(2, "big")

        if ignored_bytes:
            if not isinstance(ignored_bytes, bytes):
                raise TypeError("ignored_bytes must be bytes if set")
            if len(ignored_bytes) > pow(2, 16) - 4:
                raise ValueError(f"ignored_bytes cannot be higher than {pow(2, 16) - 4}")
            payload += len(ignored_bytes).to_bytes(2, "big") + ignored_bytes

        super().__init__(message_types["ping"], payload)
        self.num_pong_bytes = num_pong_bytes
        self.ignored_bytes = ignored_bytes

    @classmethod
    def from_bytes(cls, message):
        """Builds a PingMessage from its byte representation."""
        # Message should be at least: type (2-byte) + num_pong_bytes (2-bytes) + byteslen (2-bytes)
        message_sanity_checks(message, message_types["ping"], 6)
        num_pong_bytes = int.from_bytes(message[2:4], "big")
        byteslen = int.from_bytes(message[4:6], "big")

        if byteslen:
            ignored = message[6 : 6 + byteslen]
            if len(ignored) < byteslen:
                raise ValueError("Wrong message format. Unexpected EOF")
            if len(message) > 6 + byteslen:
                raise ValueError("Wrong data format. message has additional trailing data")
            return cls(num_pong_bytes, ignored)

        return cls(num_pong_bytes)


class PongMessage(Message):
    """
    Message to be sent in response to a ``PingMessage``.

    Args:
        ignored_bytes (:obj:`bytes`): filling bytes added to the message by the sender. Should match the ones requested
            by the sender of the ``PingMessage``.
    """

    def __init__(self, ignored_bytes=None):
        if ignored_bytes:
            if not isinstance(ignored_bytes, bytes):
                raise TypeError("ignored_bytes must be bytes if set")
            if len(ignored_bytes) > pow(2, 16) - 4:
                raise ValueError(f"ignored_bytes cannot be higher than {pow(2, 16) - 4}")

            payload = len(ignored_bytes).to_bytes(2, "big") + ignored_bytes

        else:
            payload = int.to_bytes(0, 2, "big")

        super().__init__(message_types["pong"], payload)
        self.ignored_bytes = ignored_bytes

    @classmethod
    def from_bytes(cls, message):
        """Builds a PongMessage from its byte representation."""
        # Message should be at least: type (2-byte) + byteslen (2-bytes)
        message_sanity_checks(message, message_types["pong"], 4)
        byteslen = int.from_bytes(message[2:4], "big")

        if byteslen:
            ignored_bytes = message[4 : 4 + byteslen]
            if len(ignored_bytes) < byteslen:
                raise ValueError("Wrong message format. Unexpected EOF")
            if len(message) != 4 + byteslen:
                raise ValueError("Wrong data format. message has additional trailing data")
            return cls(ignored_bytes)

        return cls()
