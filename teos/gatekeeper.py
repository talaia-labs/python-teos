from common.tools import is_compressed_pk
from common.cryptographer import Cryptographer
from common.exceptions import InvalidParameter, InvalidKey, SignatureError


class NotEnoughSlots(ValueError):
    """Raised when trying to subtract more slots than a user has available"""

    def __init__(self, user_pk, requested_slots):
        self.user_pk = user_pk
        self.requested_slots = requested_slots


class IdentificationFailure(Exception):
    """
    Raised when a user can not be identified. Either the user public key cannot be recovered or the user is
    not found within the registered ones.
    """

    pass


class UserInfo:
    def __init__(self, available_slots, subscription_end_time, appointments=None):
        self.available_slots = available_slots
        self.subscription_end_time = subscription_end_time

        if not appointments:
            self.appointments = {}
        else:
            self.appointments = appointments

    @classmethod
    def from_dict(cls, user_data):
        available_slots = user_data.get("available_slots")
        appointments = user_data.get("appointments")
        subscription_end_time = user_data.get("subscription_end_time")

        if any(v is None for v in [available_slots, appointments, subscription_end_time]):
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

    def __init__(self, user_db, block_processor, default_slots, default_subscription_duration):
        self.default_slots = default_slots
        self.block_processor = block_processor
        self.default_subscription_duration = default_subscription_duration
        self.user_db = user_db
        self.registered_users = {
            user_id: UserInfo.from_dict(user_data) for user_id, user_data in user_db.load_all_users().items()
        }

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

        return self.registered_users[user_pk].available_slots, self.registered_users[user_pk].subscription_end_time

    def identify_user(self, message, signature):
        """
        Checks if a request comes from a registered user by ec-recovering their public key from a signed message.

        Args:
            message (:obj:`bytes`): byte representation of the original message from where the signature was generated.
            signature (:obj:`str`): the user's signature (hex-encoded).

        Returns:
            :obj:`str`: a compressed key recovered from the signature and matching a registered user.

        Raises:
            :obj:`IdentificationFailure`: if the user cannot be identified.
        """

        try:
            rpk = Cryptographer.recover_pk(message, signature)
            compressed_pk = Cryptographer.get_compressed_pk(rpk)

            if compressed_pk in self.registered_users:
                return compressed_pk
            else:
                raise IdentificationFailure("User not found.")

        except (InvalidParameter, InvalidKey, SignatureError):
            raise IdentificationFailure("Wrong message or signature.")

    def fill_slots(self, user_pk, n):
        """
        Fills a given number os slots of the user subscription.

        Args:
            user_pk(:obj:`str`): the public key that identifies the user (33-bytes hex str).
            n (:obj:`int`): the number of slots to fill.

        Raises:
            :obj:`NotEnoughSlots`: if the user subscription does not have enough slots.
        """

        # DISCUSS: we may want to return a different exception if the user does not exist
        if user_pk in self.registered_users and n <= self.registered_users.get(user_pk).available_slots:
            self.registered_users[user_pk].available_slots -= n
            self.user_db.store_user(user_pk, self.registered_users[user_pk].to_dict())
        else:
            raise NotEnoughSlots(user_pk, n)

    def free_slots(self, user_pk, n):
        """
        Frees some slots of a user subscription.

        Args:
            user_pk(:obj:`str`): the public key that identifies the user (33-bytes hex str).
            n (:obj:`int`): the number of slots to free.
        """

        # DISCUSS: if the user does not exist we may want to log or return an exception.
        if user_pk in self.registered_users:
            self.registered_users[user_pk].available_slots += n
            self.user_db.store_user(user_pk, self.registered_users[user_pk].to_dict())
