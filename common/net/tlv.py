from common.tools import is_256b_hex_str

import common.net.bigsize as bigsize
from common.net.utils import message_sanity_checks

tlv_types = {
    "networks": b"\x01",
    "amt_to_forward": b"\x02",
    "outgoing_cltv_value": b"\x04",
    "short_channel_id": b"\x06",
    "payment_data": b"\x08",
}


class TLVRecord:
    """
    Base class for TLV records.

    Args:
        t (:obj:`bytes`): the message type.
        l (:obj:`bytes`): the value length.
        v (:obj:`bytes`): the message value.
    """

    def __init__(self, t=b"", l=b"", v=b""):
        if not isinstance(t, bytes):
            raise TypeError("t must be bytes")
        if not isinstance(l, bytes):
            raise TypeError("l must be bytes")
        if not isinstance(v, bytes):
            raise TypeError("v must be bytes")

        self.type = t
        self.length = l
        self.value = v

    def __len__(self):
        """Returns the length of the serialized TLV record"""
        return len(self.serialize())

    def __eq__(self, other):
        return isinstance(other, TLVRecord) and self.value == other.value

    @classmethod
    def from_bytes(cls, message):
        """
        Builds a TLV record from bytes.

        Args:
            message (:obj:`bytes`): the byte representation of the TLV record.

        Returns:
            :obj:`TLVRecord`: The TLVRecord built from the provided bytes.

        Raises:
            :obj:`TypeError`: If the provided message is not in bytes.
            :obj:`ValueError`: If the provided message is not properly encoded.
        """

        if not isinstance(message, bytes):
            raise TypeError("message must be bytes")

        try:
            t, t_length = bigsize.parse(message)
            if t.to_bytes(t_length, "big") == tlv_types["networks"]:
                return NetworksTLV.from_bytes(message)
            else:
                l, l_length = bigsize.parse(message[t_length:])
                v = message[t_length + l_length :]
                if l > len(v):
                    # Value is not long enough
                    raise ValueError()  # This message gets overwritten so it does not matter

                if len(message) != t_length + l_length + len(v):
                    # There is additional trailing data
                    raise ValueError()  # This message gets overwritten so it does not matter

                return cls(t.to_bytes(t_length, "big"), l.to_bytes(l_length, "big"), v)
        except ValueError as e:
            raise ValueError("Wrong tlv message format. Unexpected EOF")

    def serialize(self):
        """Returns the serialized representation of the TLV record."""
        return self.type + self.length + self.value


class NetworksTLV(TLVRecord):
    """
    TLV record for networks in the init message. Contains the genesis block hash of the networks the node is interested
    in.

    Args:
        networks (:obj:`list`): a list of genesis block hashes (hex str). This parameter is optional.

    Raises:
        :obj:`TypeError`: If networks is set and it is not a list.
        :obj:`ValueError`: If networks is set and all its elements are not 32-byte hex strings.
    """

    def __init__(self, networks=None):
        if not networks:
            super().__init__(tlv_types["networks"], bigsize.encode(0))
            self.networks = []
        elif isinstance(networks, list):
            chains = b""
            for chain in networks:
                if not is_256b_hex_str(chain):
                    raise ValueError("All networks must be 32-byte hex str")
                chains += bytes.fromhex(chain)
            super().__init__(tlv_types["networks"], bigsize.encode(32 * len(networks)), chains)
            self.networks = networks
        else:
            raise TypeError("networks must be a list if set")

    @classmethod
    def from_bytes(cls, message):
        """
        Builds a NetworksTLV record from bytes.

        Args:
            message (:obj:`bytes`): the byte representation of the TLV record.

        Returns:
            :obj:`NetworksTLV`: The NetworksTLV built from the provided bytes.

        Raises:
            :obj:`TypeError`: If the provided message is not in bytes or networks is not a list.
            :obj:`ValueError`: If the provided message is not properly encoded or the items in networks are not 32-byte
            hex strings.
        """

        message_sanity_checks(message, tlv_types["networks"], 2, tlv=True)

        try:
            clen, length_offset = bigsize.parse(message[1:])
        except ValueError:
            # TLV can be defined with no data.
            return cls()

        # Chains is an array of genesis block hashes (32-byte each)
        if clen % 32:
            raise ValueError(f"chains must be multiple of 32, {clen} received")

        networks = []
        offset = 1 + length_offset  # type + length fields
        for i in range(clen // 32):
            networks.append(message[offset : offset + 32].hex())
            offset += 32

        return cls(networks)
