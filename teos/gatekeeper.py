import re

SUBSCRIPTION_SLOTS = 100

# TODO: UNITTEST
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
