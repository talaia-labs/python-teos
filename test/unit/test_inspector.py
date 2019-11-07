from binascii import unhexlify

from pisa import c_logger
from pisa.errors import *
from pisa.inspector import Inspector
from pisa.appointment import Appointment
from pisa.block_processor import BlockProcessor
from test.unit.conftest import get_random_value_hex
from pisa.conf import MIN_DISPUTE_DELTA, SUPPORTED_CIPHERS, SUPPORTED_HASH_FUNCTIONS

c_logger.disabled = True

inspector = Inspector()
APPOINTMENT_OK = (0, None)

NO_HEX_STRINGS = ["R" * 64, get_random_value_hex(31) + "PP", "$" * 64, " " * 64]
WRONG_TYPES = [[], "", get_random_value_hex(32), 3.2, 2.0, (), object, {}, " " * 32, object()]
WRONG_TYPES_NO_STR = [[], unhexlify(get_random_value_hex(32)), 3.2, 2.0, (), object, {}, object()]


def test_check_locator():
    # Right appointment type, size and format
    locator = get_random_value_hex(32)
    assert Inspector.check_locator(locator) == APPOINTMENT_OK

    # Wrong size (too big)
    locator = get_random_value_hex(33)
    assert Inspector.check_locator(locator)[0] == APPOINTMENT_WRONG_FIELD_SIZE

    # Wrong size (too small)
    locator = get_random_value_hex(31)
    assert Inspector.check_locator(locator)[0] == APPOINTMENT_WRONG_FIELD_SIZE

    # Empty
    locator = None
    assert Inspector.check_locator(locator)[0] == APPOINTMENT_EMPTY_FIELD

    # Wrong type (several types tested, it should do for anything that is not a string)
    locators = [[], -1, 3.2, 0, 4, (), object, {}, object()]

    for locator in locators:
        assert Inspector.check_locator(locator)[0] == APPOINTMENT_WRONG_FIELD_TYPE

    # Wrong format (no hex)
    locators = NO_HEX_STRINGS
    for locator in locators:
        assert Inspector.check_locator(locator)[0] == APPOINTMENT_WRONG_FIELD_FORMAT


def test_check_start_time():
    # Time is defined in block height
    current_time = 100

    # Right format and right value (start time in the future)
    start_time = 101
    assert Inspector.check_start_time(start_time, current_time) == APPOINTMENT_OK

    # Start time too small (either same block or block in the past)
    start_times = [100, 99, 98, -1]
    for start_time in start_times:
        assert Inspector.check_start_time(start_time, current_time)[0] == APPOINTMENT_FIELD_TOO_SMALL

    # Empty field
    start_time = None
    assert Inspector.check_start_time(start_time, current_time)[0] == APPOINTMENT_EMPTY_FIELD

    # Wrong data type
    start_times = WRONG_TYPES
    for start_time in start_times:
        assert Inspector.check_start_time(start_time, current_time)[0] == APPOINTMENT_WRONG_FIELD_TYPE


def test_check_end_time():
    # Time is defined in block height
    current_time = 100
    start_time = 120

    # Right format and right value (start time before end and end in the future)
    end_time = 121
    assert Inspector.check_end_time(end_time, start_time, current_time) == APPOINTMENT_OK

    # End time too small (start time after end time)
    end_times = [120, 119, 118, -1]
    for end_time in end_times:
        assert Inspector.check_end_time(end_time, start_time, current_time)[0] == APPOINTMENT_FIELD_TOO_SMALL

    # End time too small (either same height as current block or in the past)
    current_time = 130
    end_times = [130, 129, 128, -1]
    for end_time in end_times:
        assert Inspector.check_end_time(end_time, start_time, current_time)[0] == APPOINTMENT_FIELD_TOO_SMALL

    # Empty field
    end_time = None
    assert Inspector.check_end_time(end_time, start_time, current_time)[0] == APPOINTMENT_EMPTY_FIELD

    # Wrong data type
    end_times = WRONG_TYPES
    for end_time in end_times:
        assert Inspector.check_end_time(end_time, start_time, current_time)[0] == APPOINTMENT_WRONG_FIELD_TYPE


def test_check_delta():
    # Right value, right format
    deltas = [MIN_DISPUTE_DELTA, MIN_DISPUTE_DELTA + 1, MIN_DISPUTE_DELTA + 1000]
    for delta in deltas:
        assert Inspector.check_delta(delta) == APPOINTMENT_OK

    # Delta too small
    deltas = [MIN_DISPUTE_DELTA - 1, MIN_DISPUTE_DELTA - 2, 0, -1, -1000]
    for delta in deltas:
        assert Inspector.check_delta(delta)[0] == APPOINTMENT_FIELD_TOO_SMALL

    # Empty field
    delta = None
    assert Inspector.check_delta(delta)[0] == APPOINTMENT_EMPTY_FIELD

    # Wrong data type
    deltas = WRONG_TYPES
    for delta in deltas:
        assert Inspector.check_delta(delta)[0] == APPOINTMENT_WRONG_FIELD_TYPE


def test_check_blob():
    # Right format and length
    encrypted_blob = get_random_value_hex(120)
    assert Inspector.check_blob(encrypted_blob) == APPOINTMENT_OK

    # # Wrong content
    # # FIXME: There is not proper defined format for this yet. It should be restricted by size at least, and check it
    # #        is multiple of the block size defined by the encryption function.

    # Wrong type
    encrypted_blobs = WRONG_TYPES_NO_STR
    for encrypted_blob in encrypted_blobs:
        assert Inspector.check_blob(encrypted_blob)[0] == APPOINTMENT_WRONG_FIELD_TYPE

    # Empty field
    encrypted_blob = None
    assert Inspector.check_blob(encrypted_blob)[0] == APPOINTMENT_EMPTY_FIELD

    # Wrong format (no hex)
    encrypted_blobs = NO_HEX_STRINGS
    for encrypted_blob in encrypted_blobs:
        assert Inspector.check_blob(encrypted_blob)[0] == APPOINTMENT_WRONG_FIELD_FORMAT


def test_check_cipher():
    # Right format and content (any case combination should be accepted)
    for cipher in SUPPORTED_CIPHERS:
        cipher_cases = [cipher, cipher.lower(), cipher.capitalize()]
        for case in cipher_cases:
            assert Inspector.check_cipher(case) == APPOINTMENT_OK

    # Wrong type
    ciphers = WRONG_TYPES_NO_STR
    for cipher in ciphers:
        assert Inspector.check_cipher(cipher)[0] == APPOINTMENT_WRONG_FIELD_TYPE

    # Wrong value
    ciphers = NO_HEX_STRINGS
    for cipher in ciphers:
        assert Inspector.check_cipher(cipher)[0] == APPOINTMENT_CIPHER_NOT_SUPPORTED

    # Empty field
    cipher = None
    assert Inspector.check_cipher(cipher)[0] == APPOINTMENT_EMPTY_FIELD


def test_check_hash_function():
    # Right format and content (any case combination should be accepted)
    for hash_function in SUPPORTED_HASH_FUNCTIONS:
        hash_function_cases = [hash_function, hash_function.lower(), hash_function.capitalize()]
        for case in hash_function_cases:
            assert Inspector.check_hash_function(case) == APPOINTMENT_OK

    # Wrong type
    hash_functions = WRONG_TYPES_NO_STR
    for hash_function in hash_functions:
        assert Inspector.check_hash_function(hash_function)[0] == APPOINTMENT_WRONG_FIELD_TYPE

    # Wrong value
    hash_functions = NO_HEX_STRINGS
    for hash_function in hash_functions:
        assert Inspector.check_hash_function(hash_function)[0] == APPOINTMENT_HASH_FUNCTION_NOT_SUPPORTED

    # Empty field
    hash_function = None
    assert Inspector.check_hash_function(hash_function)[0] == APPOINTMENT_EMPTY_FIELD


def test_inspect(run_bitcoind):
    # At this point every single check function has been already tested, let's test inspect with an invalid and a valid
    # appointments.

    # Invalid appointment, every field is empty
    appointment_data = dict()
    appointment = inspector.inspect(appointment_data)
    assert type(appointment) == tuple and appointment[0] != 0

    # Valid appointment
    locator = get_random_value_hex(32)
    start_time = BlockProcessor.get_block_count() + 5
    end_time = start_time + 20
    dispute_delta = MIN_DISPUTE_DELTA
    encrypted_blob = get_random_value_hex(64)
    cipher = SUPPORTED_CIPHERS[0]
    hash_function = SUPPORTED_HASH_FUNCTIONS[0]

    appointment_data = {
        "locator": locator,
        "start_time": start_time,
        "end_time": end_time,
        "dispute_delta": dispute_delta,
        "encrypted_blob": encrypted_blob,
        "cipher": cipher,
        "hash_function": hash_function,
    }

    appointment = inspector.inspect(appointment_data)

    assert (
        type(appointment) == Appointment
        and appointment.locator == locator
        and appointment.start_time == start_time
        and appointment.end_time == end_time
        and appointment.dispute_delta == dispute_delta
        and appointment.encrypted_blob.data == encrypted_blob
        and appointment.cipher == cipher
        and appointment.hash_function == hash_function
    )
