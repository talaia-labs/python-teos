import struct
import pyzbase32
from binascii import unhexlify

from common.tools import is_compressed_pk, is_u4int
from common.exceptions import InvalidParameter


def create_registration_receipt(user_id, available_slots, subscription_expiry):
    """
    Creates a registration receipt.

    The receipt has the following format:

        user_id (33-byte) | available_slots (4-byte) | subscription_expiry (4-byte)

    All values are big endian.

    Args:
        user_id(:obj:`str`): the public key that identifies the user (33-bytes hex str).
        available_slots (:obj:`int`): the number of slots assigned to a user subscription (4-byte unsigned int).
        subscription_expiry (:obj:`int`): the expiry assigned to a user subscription (4-byte unsigned int).

    Returns:
          :obj:`bytes`: The serialized data to be signed.
    """

    if not is_compressed_pk(user_id):
        raise InvalidParameter("Provided public key does not match expected format (33-byte hex string)")
    elif not is_u4int(available_slots):
        raise InvalidParameter("Provided available_slots must be a 4-byte unsigned integer")
    elif not is_u4int(subscription_expiry):
        raise InvalidParameter("Provided subscription_expiry must be a 4-byte unsigned integer")

    return unhexlify(user_id) + struct.pack(">I", available_slots) + struct.pack(">I", subscription_expiry)


def create_appointment_receipt(user_signature, start_block):
    """
    Creates an appointment receipt.

    The receipt has the following format:

        user_signature | start_block (4-byte)

    All values are big endian.

    Args:
        user_signature (:obj:`str`): the signature of the appointment by the user.
        start_block (:obj:`int`): the block height at which the tower will start watching for the appointment.

    Returns:
          :obj:`bytes`: The serialized data to be signed.
    """

    if not isinstance(user_signature, str):
        raise InvalidParameter("Provided user_signature is invalid")
    elif not is_u4int(start_block):
        raise InvalidParameter("Provided start_block must be a 4-byte unsigned integer")

    return pyzbase32.decode_bytes(user_signature) + struct.pack(">I", start_block)
