from math import ceil
from queue import Queue
from threading import Lock
from threading import Thread
from readerwriterlock import rwlock
from collections import OrderedDict

from teos.cleaner import Cleaner
from teos.chain_monitor import ChainMonitor
from teos.constants import OUTDATED_USERS_CACHE_SIZE_BLOCKS

from common.tools import is_compressed_pk, is_u4int
from common.cryptographer import Cryptographer
from common.receipts import create_registration_receipt
from common.constants import ENCRYPTED_BLOB_MAX_SIZE_HEX
from common.exceptions import InvalidParameter, InvalidKey, SignatureError


class NotEnoughSlots(ValueError):
    """Raised when trying to subtract more slots than a user has available."""


class AuthenticationFailure(Exception):
    """
    Raised when a user can not be authenticated. Either the user public key cannot be recovered or the user is
    not found within the registered ones.
    """


class SubscriptionExpired(ValueError):
    """Raised when trying to subtract more slots than a user has available."""


class UserInfo:
    """
    Class used to stored information about a user.

    Args:
        available_slots (:obj:`int`): the number of appointment slots available to the user.
        subscription_expiry (:obj:`int`): the block height when the user subscription will expire.
        appointments (:obj:`dict`): a dictionary containing the current appointments of the user. Optional.
    """

    def __init__(self, available_slots, subscription_expiry, appointments=None):
        self.available_slots = available_slots
        self.subscription_expiry = subscription_expiry

        if not appointments:
            # A dictionary of the form uuid:required_slots for each user appointment
            self.appointments = {}
        else:
            self.appointments = appointments

    @classmethod
    def from_dict(cls, user_data):
        """
        Creates a :obj:`UserInfo` instance from a dictionary.

        Args:
            user_data (:obj:`dict`): a dictionary containing all the necessary ``key:value`` pairs.

        Raises:
            :obj:`ValueError`: if any of the dictionary entries is missing.
        """
        available_slots = user_data.get("available_slots")
        appointments = user_data.get("appointments")
        subscription_expiry = user_data.get("subscription_expiry")

        if any(v is None for v in [available_slots, appointments, subscription_expiry]):
            raise ValueError("Wrong appointment data, some fields are missing")

        return cls(available_slots, subscription_expiry, appointments)

    def to_dict(self):
        """Converts a :obj:`UserInfo` instance in a dictionary."""
        return self.__dict__


class Gatekeeper:
    """
    The :class:`Gatekeeper` is in charge of managing the access to the tower. Only registered users are allowed to
    perform actions.

    Attributes:
        subscription_slots (:obj:`int`): The number of slots assigned to a user subscription.
        subscription_duration (:obj:`int`): The expiry assigned to a user subscription.
        expiry_delta (:obj:`int`): The grace period given to the user to renew their subscription.
        block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): A block processor instance to
            get block from bitcoind.
        user_db (:obj:`UsersDBM <teos.user_dbm.UsersDBM>`): A user database manager instance to interact with the
            database.
        registered_users (:obj:`dict`): A map of ``user_pk:user_info``.
        outdated_users_cache (:obj:`dict`): A cache of outdated user ids to allow the Watcher and Responder to query
            deleted data. Keys are bock heights, values are lists of user ids. Has a maximum size of
            ``OUTDATED_USERS_CACHE_SIZE_BLOCKS``.
        lock (:obj:`Lock`): A lock object to lock access to the Gatekeeper on updates.
    """

    def __init__(self, user_db, block_processor, subscription_slots, subscription_duration, expiry_delta):
        self.subscription_slots = subscription_slots
        self.subscription_duration = subscription_duration
        self.expiry_delta = expiry_delta
        self.block_queue = Queue()
        self.block_processor = block_processor
        self.user_db = user_db
        self.registered_users = {
            user_id: UserInfo.from_dict(user_data) for user_id, user_data in user_db.load_all_users().items()
        }
        self.outdated_users_cache = {}
        self.lock = Lock()

        # Starts a child thread to take care of expiring subscriptions
        Thread(target=self.manage_subscription_expiry, daemon=True).start()

    def manage_subscription_expiry(self):
        """
        Manages the subscription expiry of the registered users. Subscriptions are not deleted straightaway for two
        purposes:

        - First, it gives time to the ``Watcher`` and the ``Responder`` to query the necessary data for housekeeping,
        and gives some reorg protection.
        - Second, it gives a grace time to the user to renew their subscription before it is irrevocably deleted.
        """

        while True:
            block_hash = self.block_queue.get()
            # When the ChainMonitor is stopped, a final ChainMonitor.END_MESSAGE message is sent
            if block_hash == ChainMonitor.END_MESSAGE:
                break

            # Expired user deletion is delayed. Users are deleted when their subscription is outdated, not expired.
            block_height = self.block_processor.get_block(block_hash).get("height")
            self.update_outdated_users_cache(block_height)
            Cleaner.delete_outdated_users(self.get_outdated_user_ids(block_height), self.registered_users, self.user_db)

    def add_update_user(self, user_id):
        """
        Adds a new user or updates the subscription of an existing one, by adding additional slots.

        Args:
            user_id(:obj:`str`): the public key that identifies the user (33-bytes hex str).

        Returns:
            :obj:`tuple`: A tuple with the number of available slots in the user subscription, the subscription
            expiry (in absolute block height), and the registration_receipt.

        Raises:
            :obj:`InvalidParameter`: if the user_pk does not match the expected format.
        """

        if not is_compressed_pk(user_id):
            raise InvalidParameter("Provided public key does not match expected format (33-byte hex string)")

        with self.lock:
            if user_id not in self.registered_users:
                self.registered_users[user_id] = UserInfo(
                    self.subscription_slots, self.block_processor.get_block_count() + self.subscription_duration
                )
            else:
                # FIXME: For now new calls to register add subscription_slots to the current count and reset the expiry
                #  time
                if not is_u4int(self.registered_users[user_id].available_slots + self.subscription_slots):
                    raise InvalidParameter("Maximum slots reached for the subscription")

                self.registered_users[user_id].available_slots += self.subscription_slots
                self.registered_users[user_id].subscription_expiry = (
                    self.block_processor.get_block_count() + self.subscription_duration
                )

            self.user_db.store_user(user_id, self.registered_users[user_id].to_dict())
            receipt = create_registration_receipt(
                user_id,
                self.registered_users[user_id].available_slots,
                self.registered_users[user_id].subscription_expiry,
            )

        return (
            self.registered_users[user_id].available_slots,
            self.registered_users[user_id].subscription_expiry,
            receipt,
        )

    def authenticate_user(self, message, signature):
        """
        Checks if a request comes from a registered user by ec-recovering their public key from a signed message.

        Args:
            message (:obj:`bytes`): byte representation of the original message from where the signature was generated.
            signature (:obj:`str`): the user's signature (hex-encoded).

        Returns:
            :obj:`str`: A compressed key recovered from the signature and matching a registered user.

        Raises:
            :obj:`AuthenticationFailure`: if the user cannot be authenticated.
        """

        try:
            rpk = Cryptographer.recover_pk(message, signature)
            user_id = Cryptographer.get_compressed_pk(rpk)

            if user_id in self.registered_users:
                return user_id
            else:
                raise AuthenticationFailure("User not found.")

        except (InvalidParameter, InvalidKey, SignatureError):
            raise AuthenticationFailure("Wrong message or signature.")

    def add_update_appointment(self, user_id, uuid, ext_appointment):
        """
        Adds (or updates) an appointment to a user subscription. The user slots are updated accordingly.

        Slots are taken if a new appointment is given, or an update is given with an appointment bigger than the
        existing one.

        Slots are given back if an update is given but the new appointment is smaller than the existing one.

        Args:
            user_id (:obj:`str`): the public key that identifies the user (33-bytes hex str).
            uuid (:obj:`str`): the appointment uuid.
            ext_appointment (:obj:`ExtendedAppointment <teos.extended_appointment.ExtendedAppointment>`): the summary of
                new appointment the user is requesting.

        Returns:
            :obj:`int`: The number of remaining appointment slots.

        Raises:
            :obj:`NotEnoughSlots`: if the user does not have enough slots to fill.
        """

        with self.lock:
            # For updates the difference between the existing appointment and the update is computed.
            if uuid in self.registered_users[user_id].appointments:
                used_slots = self.registered_users[user_id].appointments[uuid]

            else:
                # For regular appointments 1 slot is reserved per ENCRYPTED_BLOB_MAX_SIZE_HEX block.
                used_slots = 0

            required_slots = ceil(len(ext_appointment.encrypted_blob) / ENCRYPTED_BLOB_MAX_SIZE_HEX)

            if required_slots - used_slots <= self.registered_users.get(user_id).available_slots:
                # Filling / freeing slots depending on whether this is an update or not, and if it is bigger or smaller
                # than the old appointment.
                self.registered_users.get(user_id).appointments[uuid] = required_slots
                self.registered_users.get(user_id).available_slots -= required_slots - used_slots
                self.user_db.store_user(user_id, self.registered_users[user_id].to_dict())

            else:
                raise NotEnoughSlots()

            return self.registered_users.get(user_id).available_slots

    def has_subscription_expired(self, user_id):
        """
        Checks whether a user subscription has expired at a given block_height.

        Args:
            user_id (:obj:`str`): the public key that identifies the user (33-bytes hex str).

        Returns:
            :obj:`bool`: True if the subscription has expired. False otherwise.
        """

        if user_id not in self.registered_users:
            raise AuthenticationFailure()
        return self.block_processor.get_block_count() >= self.registered_users[user_id].subscription_expiry

    def get_outdated_users(self, block_height):
        """
        Gets a dict ``user_id:appointment_uuids`` of outdated subscriptions at a given block height.

        Subscriptions are outdated ``expiry_delta`` block after expiring, giving both the internal components time to
        do their housekeeping and to the user to renew the subscription. After that period, data will be deleted.

        Args:
            block_height (:obj:`int`): the block height that wants to be checked.

        Returns:
            :obj:`dict`: A dictionary of users whose subscription is outdated at ``block_height``.
        """

        with self.lock:
            # Try to get the data from the cache
            outdated_users = self.outdated_users_cache.get(block_height)

            # Get the data from registered_users otherwise
            if not outdated_users:
                outdated_users = {
                    user_id: list(user_info.appointments.keys())
                    for user_id, user_info in self.registered_users.items()
                    if block_height == user_info.subscription_expiry + self.expiry_delta
                }

            return outdated_users

    def get_outdated_user_ids(self, block_height):
        """
        Returns a list of all user ids outdated at a given ``block_height``.

        Args:
            block_height (:obj:`int`): the block height that wants to be checked.

        Returns:
            :obj:`list`: A list of user ids whose subscription is outdated at ``block_height``.
        """

        return list(self.get_outdated_users(block_height).keys())

    def get_outdated_appointments(self, block_height):
        """
        Returns a flattened list of all appointments outdated at a given ``block_height``, indistinguishably of their
        user.

        Args:
            block_height (:obj:`int`): the block height that wants to be checked.

        Returns:
            :obj:`list`: A list of appointments whose subscription is outdated at ``block_height``.
        """

        return [
            appointment_uuid
            for user_appointments in self.get_outdated_users(block_height).values()
            for appointment_uuid in user_appointments
        ]

    def update_outdated_users_cache(self, block_height):
        """
        Adds an entry corresponding to ``block_height`` to ``outdated_users_cache`` if the entry is missing, and removes
        the oldest entry if the cache is full afterwards.

        Args:
            block_height (:obj:`int`): the block that acts as id for the new entry in the cache.
        """

        outdated_users = self.get_outdated_users(block_height)

        with self.lock:
            if block_height not in self.outdated_users_cache:
                self.outdated_users_cache[block_height] = outdated_users
                # Remove the first entry from the cache once it grows beyond the limit
                if len(self.outdated_users_cache) > OUTDATED_USERS_CACHE_SIZE_BLOCKS:
                    self.outdated_users_cache.pop(next(iter(self.outdated_users_cache)))
