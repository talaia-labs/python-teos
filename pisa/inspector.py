import re

from pisa import errors
import pisa.conf as conf
from pisa import logging, bitcoin_cli, M
from pisa.appointment import Appointment
from pisa.block_processor import BlockProcessor

# FIXME: The inspector logs the wrong messages sent form the users. A possible attack surface would be to send a really
#        long field that, even if not accepted by PISA, would be stored in the logs. This is a possible DoS surface
#        since pisa would store any kind of message (no matter the length). Solution: truncate the length of the fields
#        stored + blacklist if multiple wrong requests are received.


class Inspector:
    def inspect(self, data):
        locator = data.get('locator')
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        dispute_delta = data.get('dispute_delta')
        encrypted_blob = data.get('encrypted_blob')
        cipher = data.get('cipher')
        hash_function = data.get('hash_function')

        block_height = BlockProcessor.get_block_count()

        if block_height is not None:
            rcode, message = self.check_locator(locator)

            if rcode == 0:
                rcode, message = self.check_start_time(start_time, block_height)
            if rcode == 0:
                rcode, message = self.check_end_time(end_time, start_time, block_height)
            if rcode == 0:
                rcode, message = self.check_delta(dispute_delta)
            if rcode == 0:
                rcode, message = self.check_blob(encrypted_blob)
            if rcode == 0:
                rcode, message = self.check_cipher(cipher)
            if rcode == 0:
                rcode, message = self.check_hash_function(hash_function)

            if rcode == 0:
                r = Appointment(locator, start_time, end_time, dispute_delta, encrypted_blob, cipher, hash_function)
            else:
                r = (rcode, message)

        else:
            # In case of an unknown exception, assign a special rcode and reason.
            r = (errors.UNKNOWN_JSON_RPC_EXCEPTION, "Unexpected error occurred")

        return r

    @staticmethod
    def check_locator(locator):
        message = None
        rcode = 0

        if locator is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty locator received"
        elif type(locator) != str:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong locator data type ({})".format(type(locator))
        elif len(locator) != 64:
            rcode = errors.APPOINTMENT_WRONG_FIELD_SIZE
            message = "wrong locator size ({})".format(len(locator))
            # TODO: #12-check-txid-regexp
        elif re.search(r'^[0-9A-Fa-f]+$', locator) is None:
            rcode = errors.APPOINTMENT_WRONG_FIELD_FORMAT
            message = "wrong locator format ({})".format(locator)

        logging.error(M("[Inspector] {}".format(message)))

        return rcode, message

    @staticmethod
    def check_start_time(start_time, block_height):
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
                message = "start_time is too close to current height"

        logging.error(M("[Inspector] {}".format(message)))

        return rcode, message

    @staticmethod
    def check_end_time(end_time, start_time, block_height):
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
        elif start_time >= end_time:
            rcode = errors.APPOINTMENT_FIELD_TOO_SMALL
            if start_time > end_time:
                message = "end_time is smaller than start_time"
            else:
                message = "end_time is equal to start_time"
        elif block_height >= end_time:
            rcode = errors.APPOINTMENT_FIELD_TOO_SMALL
            if block_height > end_time:
                message = 'end_time is in the past'
            else:
                message = 'end_time is too close to current height'

        logging.error(M("[Inspector] {}".format(message)))

        return rcode, message

    @staticmethod
    def check_delta(dispute_delta):
        message = None
        rcode = 0

        t = type(dispute_delta)

        if dispute_delta is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty dispute_delta received"
        elif t != int:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong dispute_delta data type ({})".format(t)
        elif dispute_delta < conf.MIN_DISPUTE_DELTA:
            rcode = errors.APPOINTMENT_FIELD_TOO_SMALL
            message = "dispute delta too small. The dispute delta should be at least {} (current: {})".format(
                conf.MIN_DISPUTE_DELTA, dispute_delta)

        logging.error(M("[Inspector] {}".format(message)))

        return rcode, message

    # ToDo: #6-define-checks-encrypted-blob
    @staticmethod
    def check_blob(encrypted_blob):
        message = None
        rcode = 0

        t = type(encrypted_blob)

        if encrypted_blob is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty encrypted_blob received"
        elif t != str:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong encrypted_blob data type ({})".format(t)
        elif re.search(r'^[0-9A-Fa-f]+$', encrypted_blob) is None:
            rcode = errors.APPOINTMENT_WRONG_FIELD_FORMAT
            message = "wrong encrypted_blob format ({})".format(encrypted_blob)

        logging.error(M("[Inspector] {}".format(message)))

        return rcode, message

    @staticmethod
    def check_cipher(cipher):
        message = None
        rcode = 0

        t = type(cipher)

        if cipher is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty cipher received"
        elif t != str:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong cipher data type ({})".format(t)
        elif cipher.upper() not in conf.SUPPORTED_CIPHERS:
            rcode = errors.APPOINTMENT_CIPHER_NOT_SUPPORTED
            message = "cipher not supported: {}".format(cipher)

        logging.error(M("[Inspector] {}".format(message)))

        return rcode, message

    @staticmethod
    def check_hash_function(hash_function):
        message = None
        rcode = 0

        t = type(hash_function)

        if hash_function is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty hash_function received"
        elif t != str:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong hash_function data type ({})".format(t)
        elif hash_function.upper() not in conf.SUPPORTED_HASH_FUNCTIONS:
            rcode = errors.APPOINTMENT_HASH_FUNCTION_NOT_SUPPORTED
            message = "hash_function not supported {}".format(hash_function)

        logging.error(M("[Inspector] {}".format(message)))

        return rcode, message
