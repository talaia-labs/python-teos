import re
from binascii import unhexlify

import common.cryptographer
from common.constants import LOCATOR_LEN_HEX
from common.cryptographer import Cryptographer

from pisa import errors, LOG_PREFIX
from common.logger import Logger
from common.appointment import Appointment
from pisa.block_processor import BlockProcessor

logger = Logger(actor="Inspector", log_name_prefix=LOG_PREFIX)
common.cryptographer.logger = Logger(actor="Cryptographer", log_name_prefix=LOG_PREFIX)

# FIXME: The inspector logs the wrong messages sent form the users. A possible attack surface would be to send a really
#        long field that, even if not accepted by PISA, would be stored in the logs. This is a possible DoS surface
#        since pisa would store any kind of message (no matter the length). Solution: truncate the length of the fields
#        stored + blacklist if multiple wrong requests are received.


BLOCKS_IN_A_MONTH = 4320  # 4320 = roughly a month in blocks


class Inspector:
    """
    The :class:`Inspector` class is in charge of verifying that the appointment data provided by the user is correct.
    """

    def __init__(self, config):
        self.config = config

    def inspect(self, appointment_data, signature, public_key):
        """
        Inspects whether the data provided by the user is correct.

        Args:
            appointment_data (:obj:`dict`): a dictionary containing the appointment data.
            signature (:obj:`str`): the appointment signature provided by the user (hex encoded).
            public_key (:obj:`str`): the user's public key (hex encoded).

        Returns:
            :obj:`Appointment <pisa.appointment.Appointment>` or :obj:`tuple`: An appointment initialized with the
            provided data if it is correct.

            Returns a tuple ``(return code, message)`` describing the error otherwise.

            Errors are defined in :mod:`Errors <pisa.errors>`.
        """

        block_height = BlockProcessor.get_block_count()

        if block_height is not None:
            rcode, message = self.check_locator(appointment_data.get("locator"))

            if rcode == 0:
                rcode, message = self.check_start_time(appointment_data.get("start_time"), block_height)
            if rcode == 0:
                rcode, message = self.check_end_time(
                    appointment_data.get("end_time"), appointment_data.get("start_time"), block_height
                )
            if rcode == 0:
                rcode, message = self.check_to_self_delay(appointment_data.get("to_self_delay"))
            if rcode == 0:
                rcode, message = self.check_blob(appointment_data.get("encrypted_blob"))
            # if rcode == 0:
            #     rcode, message = self.check_appointment_signature(appointment_data, signature, public_key)

            if rcode == 0:
                r = Appointment.from_dict(appointment_data)
            else:
                r = (rcode, message)

        else:
            # In case of an unknown exception, assign a special rcode and reason.
            r = (errors.UNKNOWN_JSON_RPC_EXCEPTION, "Unexpected error occurred")

        return r

    @staticmethod
    def check_locator(locator):
        """
        Checks if the provided ``locator`` is correct.

        Locators must be 16-byte hex encoded strings.

        Args:
            locator (:obj:`str`): the locator to be checked.

        Returns:
            :obj:`tuple`: A tuple (return code, message) as follows:

            - ``(0, None)`` if the ``locator`` is correct.
            - ``!= (0, None)`` otherwise.

            The possible return errors are: ``APPOINTMENT_EMPTY_FIELD``, ``APPOINTMENT_WRONG_FIELD_TYPE``,
            ``APPOINTMENT_WRONG_FIELD_SIZE``, and ``APPOINTMENT_WRONG_FIELD_FORMAT``.
        """

        message = None
        rcode = 0

        if locator is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty locator received"

        elif type(locator) != str:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong locator data type ({})".format(type(locator))

        elif len(locator) != LOCATOR_LEN_HEX:
            rcode = errors.APPOINTMENT_WRONG_FIELD_SIZE
            message = "wrong locator size ({})".format(len(locator))
            # TODO: #12-check-txid-regexp

        elif re.search(r"^[0-9A-Fa-f]+$", locator) is None:
            rcode = errors.APPOINTMENT_WRONG_FIELD_FORMAT
            message = "wrong locator format ({})".format(locator)

        if message is not None:
            logger.error(message)

        return rcode, message

    @staticmethod
    def check_start_time(start_time, block_height):
        """
        Checks if the provided ``start_time`` is correct.

        Start times must be ahead the current best chain tip.

        Args:
            start_time (:obj:`int`): the block height at which the tower is requested to start watching for breaches.
            block_height (:obj:`int`): the chain height.

        Returns:
            :obj:`tuple`: A tuple (return code, message) as follows:

            - ``(0, None)`` if the ``start_time`` is correct.
            - ``!= (0, None)`` otherwise.

             The possible return errors are: ``APPOINTMENT_EMPTY_FIELD``, ``APPOINTMENT_WRONG_FIELD_TYPE``, and
             ``APPOINTMENT_FIELD_TOO_SMALL``.
        """

        message = None
        rcode = 0

        # TODO: What's too close to the current height is not properly defined. Right now any appointment that is in the
        #       future will be accepted (even if it's only one block away).

        t = type(start_time)

        if start_time is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty start_time received"

        elif t != int:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong start_time data type ({})".format(t)

        elif start_time <= block_height:
            rcode = errors.APPOINTMENT_FIELD_TOO_SMALL
            if start_time < block_height:
                message = "start_time is in the past"
            else:
                message = (
                    "start_time is too close to current height. "
                    "Accepted times are: [current_height+1, current_height+2]"
                )

        elif start_time > block_height + 6:
            rcode = errors.APPOINTMENT_FIELD_TOO_BIG
            message = "start_time is too far in the future. Accepted start times are up to 6 blocks in the future"

        if message is not None:
            logger.error(message)

        return rcode, message

    @staticmethod
    def check_end_time(end_time, start_time, block_height):
        """
        Checks if the provided ``end_time`` is correct.

        End times must be ahead both the ``start_time`` and the current best chain tip.

        Args:
            end_time (:obj:`int`): the block height at which the tower is requested to stop watching for breaches.
            start_time (:obj:`int`): the block height at which the tower is requested to start watching for breaches.
            block_height (:obj:`int`): the chain height.

        Returns:
            :obj:`tuple`: A tuple (return code, message) as follows:

            - ``(0, None)`` if the ``end_time`` is correct.
            - ``!= (0, None)`` otherwise.

            The possible return errors are: ``APPOINTMENT_EMPTY_FIELD``, ``APPOINTMENT_WRONG_FIELD_TYPE``, and
            ``APPOINTMENT_FIELD_TOO_SMALL``.
        """

        message = None
        rcode = 0

        # TODO: What's too close to the current height is not properly defined. Right now any appointment that ends in
        #       the future will be accepted (even if it's only one block away).

        t = type(end_time)

        if end_time is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty end_time received"

        elif t != int:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong end_time data type ({})".format(t)

        elif end_time > block_height + BLOCKS_IN_A_MONTH:  # 4320 = roughly a month in blocks
            rcode = errors.APPOINTMENT_FIELD_TOO_BIG
            message = "end_time should be within the next month (<= current_height + 4320)"

        elif start_time >= end_time:
            rcode = errors.APPOINTMENT_FIELD_TOO_SMALL
            if start_time > end_time:
                message = "end_time is smaller than start_time"
            else:
                message = "end_time is equal to start_time"

        elif block_height >= end_time:
            rcode = errors.APPOINTMENT_FIELD_TOO_SMALL
            if block_height > end_time:
                message = "end_time is in the past"
            else:
                message = "end_time is too close to current height"

        if message is not None:
            logger.error(message)

        return rcode, message

    def check_to_self_delay(self, to_self_delay):
        """
        Checks if the provided ``to_self_delay`` is correct.

        To self delays must be greater or equal to ``MIN_TO_SELF_DELAY``.

        Args:
            to_self_delay (:obj:`int`): The ``to_self_delay`` encoded in the ``csv`` of the ``htlc`` that this
                appointment is covering.

        Returns:
            :obj:`tuple`: A tuple (return code, message) as follows:

            - ``(0, None)`` if the ``to_self_delay`` is correct.
            - ``!= (0, None)`` otherwise.

            The possible return errors are: ``APPOINTMENT_EMPTY_FIELD``, ``APPOINTMENT_WRONG_FIELD_TYPE``, and
            ``APPOINTMENT_FIELD_TOO_SMALL``.
        """

        message = None
        rcode = 0

        t = type(to_self_delay)

        if to_self_delay is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty to_self_delay received"

        elif t != int:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong to_self_delay data type ({})".format(t)

        elif to_self_delay > pow(2, 32):
            rcode = errors.APPOINTMENT_FIELD_TOO_BIG
            message = "to_self_delay must fit the transaction nLockTime field ({} > {})".format(
                to_self_delay, pow(2, 32)
            )

        elif to_self_delay < self.config.get("MIN_TO_SELF_DELAY"):
            rcode = errors.APPOINTMENT_FIELD_TOO_SMALL
            message = "to_self_delay too small. The to_self_delay should be at least {} (current: {})".format(
                self.config.get("MIN_TO_SELF_DELAY"), to_self_delay
            )

        if message is not None:
            logger.error(message)

        return rcode, message

    # ToDo: #6-define-checks-encrypted-blob
    @staticmethod
    def check_blob(encrypted_blob):
        """
        Checks if the provided ``encrypted_blob`` may be correct.

        Args:
            encrypted_blob (:obj:`str`): the encrypted blob to be checked (hex encoded).

        Returns:
            :obj:`tuple`: A tuple (return code, message) as follows:

            - ``(0, None)`` if the ``encrypted_blob`` is correct.
            - ``!= (0, None)`` otherwise.

            The possible return errors are: ``APPOINTMENT_EMPTY_FIELD``, ``APPOINTMENT_WRONG_FIELD_TYPE``, and
            ``APPOINTMENT_WRONG_FIELD_FORMAT``.
        """

        message = None
        rcode = 0

        t = type(encrypted_blob)

        if encrypted_blob is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty encrypted_blob received"

        elif t != str:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong encrypted_blob data type ({})".format(t)

        elif re.search(r"^[0-9A-Fa-f]+$", encrypted_blob) is None:
            rcode = errors.APPOINTMENT_WRONG_FIELD_FORMAT
            message = "wrong encrypted_blob format ({})".format(encrypted_blob)

        if message is not None:
            logger.error(message)

        return rcode, message

    @staticmethod
    # Verifies that the appointment signature is a valid signature with public key
    def check_appointment_signature(appointment_data, signature, pk_der):
        """
        Checks if the provided user signature is correct.

        Args:
            appointment_data (:obj:`dict`): the appointment that was signed by the user.
            signature (:obj:`str`): the user's signature (hex encoded).
            pk_der (:obj:`str`): the user's public key (hex encoded, DER format).

        Returns:
            :obj:`tuple`: A tuple (return code, message) as follows:

            - ``(0, None)`` if the ``signature`` is correct.
            - ``!= (0, None)`` otherwise.

            The possible return errors are: ``APPOINTMENT_EMPTY_FIELD``, ``APPOINTMENT_WRONG_FIELD_TYPE``, and
            ``APPOINTMENT_WRONG_FIELD_FORMAT``.
        """

        message = None
        rcode = 0

        if signature is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty signature received"

        elif pk_der is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty public key received"

        else:
            pk = Cryptographer.load_public_key_der(unhexlify(pk_der))
            valid_sig = Cryptographer.verify(Appointment.from_dict(appointment_data).serialize(), signature, pk)

            if not valid_sig:
                rcode = errors.APPOINTMENT_INVALID_SIGNATURE
                message = "invalid signature"

        return rcode, message
