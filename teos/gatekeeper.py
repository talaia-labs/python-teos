import re

import teos.errors as errors

from common.appointment import Appointment
from common.cryptographer import Cryptographer

SUBSCRIPTION_SLOTS = 1

# TODO: UNITTEST, DOCS
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

    def fill_subscription_slots(self, user_pk, n):
        slots = self.registered_users.get(user_pk)

        # FIXME: This looks pretty dangerous. I'm guessing race conditions can happen here.
        if slots == n:
            self.registered_users.pop(user_pk)
        else:
            self.registered_users[user_pk] -= n

    def identify_user(self, appointment_data, signature):
        """
        Checks if the provided user signature is comes from a registered user with available appointment slots.

        Args:
            appointment_data (:obj:`dict`): the appointment that was signed by the user.
            signature (:obj:`str`): the user's signature (hex encoded).

        Returns:
            :obj:`tuple`: A tuple (return code, message) as follows:

            - ``(0, None)`` if the user can be identified (recovered pk belongs to a registered user) and the user has
                available slots.
            - ``!= (0, None)`` otherwise.

            The possible return errors are: ``APPOINTMENT_EMPTY_FIELD`` and ``APPOINTMENT_INVALID_SIGNATURE``.
        """

        if signature is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty signature received"

        else:
            appointment = Appointment.from_dict(appointment_data)
            rpk = Cryptographer.recover_pk(appointment.serialize(), signature)
            compressed_user_pk = Cryptographer.get_compressed_pk(rpk)

            if compressed_user_pk and compressed_user_pk in self.registered_users:
                rcode = 0
                message = compressed_user_pk

            else:
                rcode = errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS
                message = "invalid signature or the user does not have enough slots available"

        return rcode, message

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
