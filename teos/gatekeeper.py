import re

from common.appointment import Appointment
from common.cryptographer import Cryptographer

SUBSCRIPTION_SLOTS = 1


# TODO: UNITTEST, DOCS
class NotEnoughSlots(ValueError):
    """Raise this when trying to subtract more slots than a user has available"""

    pass


class Gatekeeper:
    def __init__(self):
        self.registered_users = {}

    @staticmethod
    def check_user_pk(user_pk):
        """
        Checks if a given value is a 33-byte hex encoded string.

        Args:
            user_pk(:mod:`str`): the value to be checked.

        Returns:
            :obj:`bool`: Whether or not the value matches the format.
        """
        return isinstance(user_pk, str) and re.match(r"^[0-9A-Fa-f]{66}$", user_pk) is not None

    def add_update_user(self, user_pk):
        if not self.check_user_pk(user_pk):
            raise ValueError("provided public key does not match expected format (33-byte hex string)")

        if user_pk not in self.registered_users:
            self.registered_users[user_pk] = SUBSCRIPTION_SLOTS
        else:
            self.registered_users[user_pk] += SUBSCRIPTION_SLOTS

        return self.registered_users[user_pk]

    def identify_user(self, appointment_data, signature):
        """
        Checks if the provided user signature is comes from a registered user with available appointment slots.

        Args:
            appointment_data (:obj:`dict`): the appointment that was signed by the user.
            signature (:obj:`str`): the user's signature (hex encoded).

        Returns:
            :obj:`str` or `None`: a compressed key if it can be recovered from the signature and matches a registered
            user. ``None`` otherwise.
        """

        user_pk = None

        if signature is not None:
            appointment = Appointment.from_dict(appointment_data)
            rpk = Cryptographer.recover_pk(appointment.serialize(), signature)
            compressed_pk = Cryptographer.get_compressed_pk(rpk)

            if compressed_pk in self.registered_users and self.registered_users.get(compressed_pk) > 0:
                user_pk = compressed_pk

        return user_pk

    def get_slots(self, user_pk):
        """
        Returns the number os available slots for a given user.

        Args:
            user_pk(:mod:`str`): the public key that identifies the user (33-bytes hex str)

        Returns:
            :obj:`int`: the number of available slots.

        """
        slots = self.registered_users.get(user_pk)
        return slots if slots is not None else 0

    def fill_slots(self, user_pk, n):
        if n >= self.registered_users.get(user_pk):
            self.registered_users[user_pk] -= n
        else:
            raise NotEnoughSlots("No enough empty slots")

    def free_slots(self, user_pk, n):
        self.registered_users[user_pk] += n
