import re

from common.cryptographer import Cryptographer

SUBSCRIPTION_SLOTS = 1


# TODO: UNITTEST
class NotEnoughSlots(ValueError):
    """Raise this when trying to subtract more slots than a user has available."""

    def __init__(self, user_pk, requested_slots):
        self.user_pk = user_pk
        self.requested_slots = requested_slots


class IdentificationFailure(Exception):
    """
    Raise this when a user can not be identified. Either the user public key cannot be recovered or the user is
    not found within the registered ones.
    """

    pass


class Gatekeeper:
    """
    The Gatekeeper is in charge of managing the access to the tower. Only registered users are allowed to perform
    actions.

    Attributes:
        registered_users (:obj:`dict`): a map of user_pk:appointment_slots.
    """

    def __init__(self):
        self.registered_users = {}

    @staticmethod
    def check_user_pk(user_pk):
        """
        Checks if a given value is a 33-byte hex encoded string.

        Args:
            user_pk(:obj:`str`): the value to be checked.

        Returns:
            :obj:`bool`: Whether or not the value matches the format.
        """

        return isinstance(user_pk, str) and re.match(r"^[0-9A-Fa-f]{66}$", user_pk) is not None

    def add_update_user(self, user_pk):
        """
        Adds a new user or updates the subscription of an existing one, by adding additional slots.

        Args:
            user_pk(:obj:`str`): the public key that identifies the user (33-bytes hex str).

        Returns:
            :obj:`int`: the number of avaiable slots in the user subscription.
        """

        if not self.check_user_pk(user_pk):
            raise ValueError("provided public key does not match expected format (33-byte hex string)")

        if user_pk not in self.registered_users:
            self.registered_users[user_pk] = SUBSCRIPTION_SLOTS
        else:
            self.registered_users[user_pk] += SUBSCRIPTION_SLOTS

        return self.registered_users[user_pk]

    def identify_user(self, message, signature):
        """
        Checks if the provided user signature comes from a registered user.

        Args:
            message (:obj:`bytes`): byte representation of the original message from where the signature was generated.
            signature (:obj:`str`): the user's signature (hex encoded).

        Returns:
            :obj:`str`: a compressed key recovered from the signature and matching a registered user.

        Raises:
            :obj:`<teos.gatekeeper.IdentificationFailure>`: if the user cannot be identified.
        """

        if isinstance(message, bytes) and isinstance(signature, str):
            rpk = Cryptographer.recover_pk(message, signature)
            compressed_pk = Cryptographer.get_compressed_pk(rpk)

            if compressed_pk in self.registered_users:
                return compressed_pk
            else:
                raise IdentificationFailure("User not found.")

        else:
            raise IdentificationFailure("Wrong message or signature.")

    def fill_slots(self, user_pk, n):
        """
        Fills a given number os slots of the user subscription.

        Args:
            user_pk(:obj:`str`): the public key that identifies the user (33-bytes hex str).
            n: the number of slots to fill.

        Raises:
            :obj:`<teos.gatekeeper.NotEnoughSlots>`: if the user subscription does not have enough slots.
        """

        if n <= self.registered_users.get(user_pk):
            self.registered_users[user_pk] -= n
        else:
            raise NotEnoughSlots(user_pk, n)

    def free_slots(self, user_pk, n):
        """
        Frees some slots of a user subscription.

        Args:
            user_pk(:obj:`str`): the public key that identifies the user (33-bytes hex str).
            n: the number of slots to free.
        """

        self.registered_users[user_pk] += n
