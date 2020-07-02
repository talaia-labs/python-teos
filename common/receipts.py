import struct
from binascii import unhexlify

from common.tools import is_compressed_pk
from common.exceptions import InvalidParameter


def create_registration_receipt(user_id, available_slots, subscription_expiry):
    if not is_compressed_pk(user_id):
        raise InvalidParameter("Provided public key does not match expected format (33-byte hex string)")
    if not isinstance(available_slots, int):
        raise InvalidParameter("Provided available_slots must be an integer")
    if not isinstance(subscription_expiry, int):
        raise InvalidParameter("Provided subscription_expiry must be an integer")

    return unhexlify(user_id) + struct.pack(">I", available_slots) + struct.pack(">I", subscription_expiry)


def create_appointment_receipt():
    pass
