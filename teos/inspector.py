import re

from common.logger import Logger
from common.tools import is_locator
from common.constants import LOCATOR_LEN_HEX
from common.appointment import Appointment

from teos import errors, LOG_PREFIX

logger = Logger(actor="Inspector", log_name_prefix=LOG_PREFIX)

# FIXME: The inspector logs the wrong messages sent form the users. A possible attack surface would be to send a really
#        long field that, even if not accepted by TEOS, would be stored in the logs. This is a possible DoS surface
#        since teos would store any kind of message (no matter the length). Solution: truncate the length of the fields
#        stored + blacklist if multiple wrong requests are received.


BLOCKS_IN_A_MONTH = 4320  # 4320 = roughly a month in blocks


class InspectionFailed(Exception):
    """Raise this the inspector finds a problem with any of the appointment fields"""

    def __init__(self, erno, reason):
        self.erno = erno
        self.reason = reason


class Inspector:
    """
    The :class:`Inspector` class is in charge of verifying that the appointment data provided by the user is correct.

    Args:
        block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): a ``BlockProcessor`` instance.
        min_to_self_delay (:obj:`int`): the minimum to_self_delay accepted in appointments.

    """

    def __init__(self, block_processor, min_to_self_delay):
        self.block_processor = block_processor
        self.min_to_self_delay = min_to_self_delay

    def inspect(self, appointment_data):
        """
        Inspects whether the data provided by the user is correct.

        Args:
            appointment_data (:obj:`dict`): a dictionary containing the appointment data.


        Returns:
            :obj:`Appointment <teos.appointment.Appointment>`: An appointment initialized with the provided data.

        Raises:
           :obj:`InspectionFailed`: if any of the fields is wrong.
        """

        if appointment_data is None:
            raise InspectionFailed(errors.APPOINTMENT_EMPTY_FIELD, "empty appointment received")
        elif not isinstance(appointment_data, dict):
            raise InspectionFailed(errors.APPOINTMENT_WRONG_FIELD, "wrong appointment format")

        block_height = self.block_processor.get_block_count()
        if block_height is None:
            raise InspectionFailed(errors.UNKNOWN_JSON_RPC_EXCEPTION, "unexpected error occurred")

        self.check_locator(appointment_data.get("locator"))
        self.check_start_time(appointment_data.get("start_time"), block_height)
        self.check_end_time(appointment_data.get("end_time"), appointment_data.get("start_time"), block_height)
        self.check_to_self_delay(appointment_data.get("to_self_delay"))
        self.check_blob(appointment_data.get("encrypted_blob"))

        return Appointment.from_dict(appointment_data)

    @staticmethod
    def check_locator(locator):
        """
        Checks if the provided ``locator`` is correct.

        Locators must be 16-byte hex-encoded strings.

        Args:
            locator (:obj:`str`): the locator to be checked.

        Raises:
           :obj:`InspectionFailed`: if any of the fields is wrong.
        """

        if locator is None:
            raise InspectionFailed(errors.APPOINTMENT_EMPTY_FIELD, "empty locator received")

        elif type(locator) != str:
            raise InspectionFailed(
                errors.APPOINTMENT_WRONG_FIELD_TYPE, "wrong locator data type ({})".format(type(locator))
            )

        elif len(locator) != LOCATOR_LEN_HEX:
            raise InspectionFailed(errors.APPOINTMENT_WRONG_FIELD_SIZE, "wrong locator size ({})".format(len(locator)))

        elif not is_locator(locator):
            raise InspectionFailed(errors.APPOINTMENT_WRONG_FIELD_FORMAT, "wrong locator format ({})".format(locator))

    @staticmethod
    def check_start_time(start_time, block_height):
        """
        Checks if the provided ``start_time`` is correct.

        Start times must be ahead the current best chain tip.

        Args:
            start_time (:obj:`int`): the block height at which the tower is requested to start watching for breaches.
            block_height (:obj:`int`): the chain height.

        Raises:
           :obj:`InspectionFailed`: if any of the fields is wrong.
        """

        if start_time is None:
            raise InspectionFailed(errors.APPOINTMENT_EMPTY_FIELD, "empty start_time received")

        elif type(start_time) != int:
            raise InspectionFailed(
                errors.APPOINTMENT_WRONG_FIELD_TYPE, "wrong start_time data type ({})".format(type(start_time))
            )

        elif start_time < block_height:
            raise InspectionFailed(errors.APPOINTMENT_FIELD_TOO_SMALL, "start_time is in the past")

        elif start_time == block_height:
            raise InspectionFailed(
                errors.APPOINTMENT_FIELD_TOO_SMALL,
                "start_time is too close to current height. Accepted times are: [current_height+1, current_height+6]",
            )

        elif start_time > block_height + 6:
            raise InspectionFailed(
                errors.APPOINTMENT_FIELD_TOO_BIG,
                "start_time is too far in the future. Accepted start times are up to 6 blocks in the future",
            )

    @staticmethod
    def check_end_time(end_time, start_time, block_height):
        """
        Checks if the provided ``end_time`` is correct.

        End times must be ahead both the ``start_time`` and the current best chain tip.

        Args:
            end_time (:obj:`int`): the block height at which the tower is requested to stop watching for breaches.
            start_time (:obj:`int`): the block height at which the tower is requested to start watching for breaches.
            block_height (:obj:`int`): the chain height.

        Raises:
           :obj:`InspectionFailed`: if any of the fields is wrong.
        """

        # TODO: What's too close to the current height is not properly defined. Right now any appointment that ends in
        #       the future will be accepted (even if it's only one block away).

        if end_time is None:
            raise InspectionFailed(errors.APPOINTMENT_EMPTY_FIELD, "empty end_time received")

        elif type(end_time) != int:
            raise InspectionFailed(
                errors.APPOINTMENT_WRONG_FIELD_TYPE, "wrong end_time data type ({})".format(type(end_time))
            )

        elif end_time > block_height + BLOCKS_IN_A_MONTH:  # 4320 = roughly a month in blocks
            raise InspectionFailed(
                errors.APPOINTMENT_FIELD_TOO_BIG, "end_time should be within the next month (<= current_height + 4320)"
            )
        elif start_time > end_time:
            raise InspectionFailed(errors.APPOINTMENT_FIELD_TOO_SMALL, "end_time is smaller than start_time")

        elif start_time == end_time:
            raise InspectionFailed(errors.APPOINTMENT_FIELD_TOO_SMALL, "end_time is equal to start_time")

        elif block_height > end_time:
            raise InspectionFailed(errors.APPOINTMENT_FIELD_TOO_SMALL, "end_time is in the past")

        elif block_height == end_time:
            raise InspectionFailed(errors.APPOINTMENT_FIELD_TOO_SMALL, "end_time is too close to current height")

    def check_to_self_delay(self, to_self_delay):
        """
        Checks if the provided ``to_self_delay`` is correct.

        To self delays must be greater or equal to ``MIN_TO_SELF_DELAY``.

        Args:
            to_self_delay (:obj:`int`): The ``to_self_delay`` encoded in the ``csv`` of ``to_remote`` output of the
                commitment transaction this appointment is covering.

        Raises:
           :obj:`InspectionFailed`: if any of the fields is wrong.
        """

        if to_self_delay is None:
            raise InspectionFailed(errors.APPOINTMENT_EMPTY_FIELD, "empty to_self_delay received")

        elif type(to_self_delay) != int:
            raise InspectionFailed(
                errors.APPOINTMENT_WRONG_FIELD_TYPE, "wrong to_self_delay data type ({})".format(type(to_self_delay))
            )

        elif to_self_delay > pow(2, 32):
            raise InspectionFailed(
                errors.APPOINTMENT_FIELD_TOO_BIG,
                "to_self_delay must fit the transaction nLockTime field ({} > {})".format(to_self_delay, pow(2, 32)),
            )

        elif to_self_delay < self.min_to_self_delay:
            raise InspectionFailed(
                errors.APPOINTMENT_FIELD_TOO_SMALL,
                "to_self_delay too small. The to_self_delay should be at least {} (current: {})".format(
                    self.min_to_self_delay, to_self_delay
                ),
            )

    # ToDo: #6-define-checks-encrypted-blob
    @staticmethod
    def check_blob(encrypted_blob):
        """
        Checks if the provided ``encrypted_blob`` may be correct.

        Args:
            encrypted_blob (:obj:`str`): the encrypted blob to be checked (hex-encoded).

        Raises:
           :obj:`InspectionFailed`: if any of the fields is wrong.
        """

        if encrypted_blob is None:
            raise InspectionFailed(errors.APPOINTMENT_EMPTY_FIELD, "empty encrypted_blob received")

        elif type(encrypted_blob) != str:
            raise InspectionFailed(
                errors.APPOINTMENT_WRONG_FIELD_TYPE, "wrong encrypted_blob data type ({})".format(type(encrypted_blob))
            )

        elif re.search(r"^[0-9A-Fa-f]+$", encrypted_blob) is None:
            raise InspectionFailed(
                errors.APPOINTMENT_WRONG_FIELD_FORMAT, "wrong encrypted_blob format ({})".format(encrypted_blob)
            )
