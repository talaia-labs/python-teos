from math import ceil
from threading import Lock

from common.tools import is_compressed_pk
from common.cryptographer import Cryptographer
from common.constants import ENCRYPTED_BLOB_MAX_SIZE_HEX
from common.exceptions import InvalidParameter, InvalidKey, SignatureError


class NotEnoughSlots(ValueError):
    """Raised when trying to subtract more slots than a user has available"""

    pass


class AuthenticationFailure(Exception):
    """
    Raised when a user can not be authenticated. Either the user public key cannot be recovered or the user is
    not found within the registered ones.
    """

    pass


class UserInfo:
    def __init__(self, available_slots, subscription_expiry, appointments=None):
        self.available_slots = available_slots
        self.subscription_expiry = subscription_expiry

        if not appointments:
            self.appointments = []
        else:
            self.appointments = appointments

    @classmethod
    def from_dict(cls, user_data):
        available_slots = user_data.get("available_slots")
        appointments = user_data.get("appointments")
        subscription_expiry = user_data.get("subscription_expiry")

        if any(v is None for v in [available_slots, appointments, subscription_expiry]):
            raise ValueError("Wrong appointment data, some fields are missing")

        return cls(available_slots, subscription_expiry, appointments)

    def to_dict(self):
        return self.__dict__


class Gatekeeper:
    """
    The :class:`Gatekeeper` is in charge of managing the access to the tower. Only registered users are allowed to
    perform actions.

    Attributes:
        registered_users (:obj:`dict`): a map of user_pk:UserInfo.
    """

    def __init__(self, user_db, block_processor, default_slots, default_subscription_duration, expiry_delta):
        self.default_slots = default_slots
        self.default_subscription_duration = default_subscription_duration
        self.expiry_delta = expiry_delta
        self.block_processor = block_processor
        self.user_db = user_db
        self.registered_users = {
            user_id: UserInfo.from_dict(user_data) for user_id, user_data in user_db.load_all_users().items()
        }
        self.lock = Lock()

    def add_update_user(self, user_pk):
        """
        Adds a new user or updates the subscription of an existing one, by adding additional slots.

        Args:
            user_pk(:obj:`str`): the public key that identifies the user (33-bytes hex str).

        Returns:
            :obj:`tuple`: a tuple with the number of available slots in the user subscription and the subscription end
            time (in absolute block height).
        """

        if not is_compressed_pk(user_pk):
            raise ValueError("Provided public key does not match expected format (33-byte hex string)")

        if user_pk not in self.registered_users:
            self.registered_users[user_pk] = UserInfo(
                self.default_slots, self.block_processor.get_block_count() + self.default_subscription_duration
            )
        else:
            # FIXME: For now new calls to register add default_slots to the current count and reset the expiry time
            self.registered_users[user_pk].available_slots += self.default_slots
            self.registered_users[user_pk].subscription_expiry = (
                self.block_processor.get_block_count() + self.default_subscription_duration
            )

        self.user_db.store_user(user_pk, self.registered_users[user_pk].to_dict())

        return self.registered_users[user_pk].available_slots, self.registered_users[user_pk].subscription_expiry

    def authenticate_user(self, message, signature):
        """
        Checks if a request comes from a registered user by ec-recovering their public key from a signed message.

        Args:
            message (:obj:`bytes`): byte representation of the original message from where the signature was generated.
            signature (:obj:`str`): the user's signature (hex-encoded).

        Returns:
            :obj:`str`: a compressed key recovered from the signature and matching a registered user.

        Raises:
            :obj:`AuthenticationFailure`: if the user cannot be authenticated.
        """

        try:
            rpk = Cryptographer.recover_pk(message, signature)
            compressed_pk = Cryptographer.get_compressed_pk(rpk)

            if compressed_pk in self.registered_users:
                return compressed_pk
            else:
                raise AuthenticationFailure("User not found.")

        except (InvalidParameter, InvalidKey, SignatureError):
            raise AuthenticationFailure("Wrong message or signature.")

    def update_available_slots(self, user_id, new_appointment, old_appointment=None):
        self.lock.acquire()
        if old_appointment:
            # For updates the difference between the existing appointment and the update is computed.
            used_slots = ceil(new_appointment.get("size") / ENCRYPTED_BLOB_MAX_SIZE_HEX)
            required_slots = ceil(old_appointment.get("size") / ENCRYPTED_BLOB_MAX_SIZE_HEX) - used_slots
        else:
            # For regular appointments 1 slot is reserved per ENCRYPTED_BLOB_MAX_SIZE_HEX block.
            required_slots = ceil(new_appointment.get("size") / ENCRYPTED_BLOB_MAX_SIZE_HEX)

        if required_slots <= self.registered_users.get(user_id).available_slots:
            # Filling / freeing slots depending on whether this is an update or not, and if it is bigger or smaller than
            # the old appointment.
            self.registered_users.get(user_id).available_slots -= required_slots
        else:
            self.lock.release()
            raise NotEnoughSlots()

        self.lock.release()
        return self.registered_users.get(user_id).available_slots

    def get_expiring_appointments(self, block_height):
        expiring_appointments = []
        for user_id, user_info in self.registered_users.items():
            if block_height > user_info.subscription_expiry + self.expiry_delta:
                expiring_appointments.extend(user_info.appointments)
