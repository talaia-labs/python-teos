import re
import pisa.conf as conf
from pisa import errors
from pisa import logging, bitcoin_cli
from pisa.appointment import Appointment
from pisa.utils.auth_proxy import JSONRPCException


class Inspector:
    def inspect(self, data):
        locator = data.get('locator')
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        dispute_delta = data.get('dispute_delta')
        encrypted_blob = data.get('encrypted_blob')
        cipher = data.get('cipher')
        hash_function = data.get('hash_function')

        try:
            block_height = bitcoin_cli.getblockcount()

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

        except JSONRPCException as e:
            logging.error("[Inspector] JSONRPCException. Error code {}".format(e))

            # In case of an unknown exception, assign a special rcode and reason.
            r = (errors.UNKNOWN_JSON_RPC_EXCEPTION, "Unexpected error occurred")

        return r

    def check_locator(self, locator):
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

        logging.error("[Inspector] {}".format(message))

        return rcode, message

    def check_start_time(self, start_time, block_height):
        message = None
        rcode = 0

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
                message = "start_time too close to current height"

        logging.error("[Inspector] {}".format(message))

        return rcode, message

    def check_end_time(self, end_time, start_time, block_height):
        message = None
        rcode = 0

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
        elif block_height > end_time:
            rcode = errors.APPOINTMENT_FIELD_TOO_SMALL
            message = 'end_time is in the past'

        logging.error("[Inspector] {}".format(message))

        return rcode, message

    def check_delta(self, dispute_delta):
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

        logging.error("[Inspector] {}".format(message))

        return rcode, message

    # ToDo: #6-define-checks-encrypted-blob
    def check_blob(self, encrypted_blob):
        message = None
        rcode = 0

        t = type(encrypted_blob)

        if encrypted_blob is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty encrypted_blob received"
        elif t != str:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong encrypted_blob data type ({})".format(t)
        elif encrypted_blob == '':
            # ToDo: #6 We may want to define this to be at least as long as one block of the cipher we are using
            rcode = errors.APPOINTMENT_WRONG_FIELD
            message = "wrong encrypted_blob"

        logging.error("[Inspector] {}".format(message))

        return rcode, message

    def check_cipher(self, cipher):
        message = None
        rcode = 0

        t = type(cipher)

        if cipher is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty cipher received"
        elif t != str:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong cipher data type ({})".format(t)
        elif cipher not in conf.SUPPORTED_CIPHERS:
            rcode = errors.APPOINTMENT_CIPHER_NOT_SUPPORTED
            message = "cipher not supported: {}".format(cipher)

        logging.error("[Inspector] {}".format(message))

        return rcode, message

    def check_hash_function(self, hash_function):
        message = None
        rcode = 0

        t = type(hash_function)

        if hash_function is None:
            rcode = errors.APPOINTMENT_EMPTY_FIELD
            message = "empty hash_function received"
        elif t != str:
            rcode = errors.APPOINTMENT_WRONG_FIELD_TYPE
            message = "wrong hash_function data type ({})".format(t)
        elif hash_function not in conf.SUPPORTED_HASH_FUNCTIONS:
            rcode = errors.APPOINTMENT_HASH_FUNCTION_NOT_SUPPORTED
            message = "hash_function not supported {}".format(hash_function)

        logging.error("[Inspector] {}".format(message))

        return rcode, message
