import pytest
from binascii import unhexlify

import teos.errors as errors
from teos import LOG_PREFIX
from teos.block_processor import BlockProcessor
from teos.inspector import Inspector, InspectionFailed

import common.cryptographer
from common.logger import Logger
from common.appointment import Appointment
from common.constants import LOCATOR_LEN_BYTES, LOCATOR_LEN_HEX

from test.teos.unit.conftest import get_random_value_hex, bitcoind_connect_params, get_config

common.cryptographer.logger = Logger(actor="Cryptographer", log_name_prefix=LOG_PREFIX)

NO_HEX_STRINGS = [
    "R" * LOCATOR_LEN_HEX,
    get_random_value_hex(LOCATOR_LEN_BYTES - 1) + "PP",
    "$" * LOCATOR_LEN_HEX,
    " " * LOCATOR_LEN_HEX,
]
WRONG_TYPES = [
    [],
    "",
    get_random_value_hex(LOCATOR_LEN_BYTES),
    3.2,
    2.0,
    (),
    object,
    {},
    " " * LOCATOR_LEN_HEX,
    object(),
]
WRONG_TYPES_NO_STR = [[], unhexlify(get_random_value_hex(LOCATOR_LEN_BYTES)), 3.2, 2.0, (), object, {}, object()]

config = get_config()
MIN_TO_SELF_DELAY = config.get("MIN_TO_SELF_DELAY")
block_processor = BlockProcessor(bitcoind_connect_params)
inspector = Inspector(block_processor, MIN_TO_SELF_DELAY)


def test_check_locator():
    # Right appointment type, size and format
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    assert inspector.check_locator(locator) is None

    # Wrong size (too big)
    locator = get_random_value_hex(LOCATOR_LEN_BYTES + 1)
    with pytest.raises(InspectionFailed):
        try:
            inspector.check_locator(locator)

        except InspectionFailed as e:
            assert e.erno == errors.APPOINTMENT_WRONG_FIELD_SIZE
            raise e

    # Wrong size (too small)
    locator = get_random_value_hex(LOCATOR_LEN_BYTES - 1)
    with pytest.raises(InspectionFailed):
        try:
            inspector.check_locator(locator)

        except InspectionFailed as e:
            assert e.erno == errors.APPOINTMENT_WRONG_FIELD_SIZE
            raise e

    # Empty
    locator = None
    with pytest.raises(InspectionFailed):
        try:
            inspector.check_locator(locator)

        except InspectionFailed as e:
            assert e.erno == errors.APPOINTMENT_EMPTY_FIELD
            raise e

    # Wrong type (several types tested, it should do for anything that is not a string)
    locators = [[], -1, 3.2, 0, 4, (), object, {}, object()]

    for locator in locators:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_locator(locator)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_WRONG_FIELD_TYPE
                raise e

    # Wrong format (no hex)
    locators = NO_HEX_STRINGS
    for locator in locators:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_locator(locator)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_WRONG_FIELD_FORMAT
                raise e


def test_check_start_time():
    # Time is defined in block height
    current_time = 100

    # Right format and right value (start time in the future)
    start_time = 101
    assert inspector.check_start_time(start_time, current_time) is None

    # Start time too small (either same block or block in the past)
    start_times = [100, 99, 98, -1]
    for start_time in start_times:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_start_time(start_time, current_time)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_FIELD_TOO_SMALL
                raise e

    # Empty field
    start_time = None
    with pytest.raises(InspectionFailed):
        try:
            inspector.check_start_time(start_time, current_time)

        except InspectionFailed as e:
            assert e.erno == errors.APPOINTMENT_EMPTY_FIELD
            raise e

    # Wrong data type
    start_times = WRONG_TYPES
    for start_time in start_times:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_start_time(start_time, current_time)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_WRONG_FIELD_TYPE
                raise e


def test_check_end_time():
    # Time is defined in block height
    current_time = 100
    start_time = 120

    # Right format and right value (start time before end and end in the future)
    end_time = 121
    assert inspector.check_end_time(end_time, start_time, current_time) is None

    # End time too small (start time after end time)
    end_times = [120, 119, 118, -1]
    for end_time in end_times:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_end_time(end_time, start_time, current_time)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_FIELD_TOO_SMALL
                raise e

    # End time too small (either same height as current block or in the past)
    current_time = 130
    end_times = [130, 129, 128, -1]
    for end_time in end_times:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_end_time(end_time, start_time, current_time)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_FIELD_TOO_SMALL
                raise e

    # Empty field
    end_time = None
    with pytest.raises(InspectionFailed):
        try:
            inspector.check_end_time(end_time, start_time, current_time)

        except InspectionFailed as e:
            assert e.erno == errors.APPOINTMENT_EMPTY_FIELD
            raise e

    # Wrong data type
    end_times = WRONG_TYPES
    for end_time in end_times:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_end_time(end_time, start_time, current_time)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_WRONG_FIELD_TYPE
                raise e


def test_check_to_self_delay():
    # Right value, right format
    to_self_delays = [MIN_TO_SELF_DELAY, MIN_TO_SELF_DELAY + 1, MIN_TO_SELF_DELAY + 1000]
    for to_self_delay in to_self_delays:
        assert inspector.check_to_self_delay(to_self_delay) is None

    # to_self_delay too small
    to_self_delays = [MIN_TO_SELF_DELAY - 1, MIN_TO_SELF_DELAY - 2, 0, -1, -1000]
    for to_self_delay in to_self_delays:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_to_self_delay(to_self_delay)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_FIELD_TOO_SMALL
                raise e

    # Empty field
    to_self_delay = None
    with pytest.raises(InspectionFailed):
        try:
            inspector.check_to_self_delay(to_self_delay)

        except InspectionFailed as e:
            assert e.erno == errors.APPOINTMENT_EMPTY_FIELD
            raise e

    # Wrong data type
    to_self_delays = WRONG_TYPES
    for to_self_delay in to_self_delays:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_to_self_delay(to_self_delay)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_WRONG_FIELD_TYPE
                raise e


def test_check_blob():
    # Right format and length
    encrypted_blob = get_random_value_hex(120)
    assert inspector.check_blob(encrypted_blob) is None

    # # Wrong content
    # # FIXME: There is not proper defined format for this yet. It should be restricted by size at least, and check it
    # #        is multiple of the block size defined by the encryption function.

    # Wrong type
    encrypted_blobs = WRONG_TYPES_NO_STR
    for encrypted_blob in encrypted_blobs:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_blob(encrypted_blob)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_WRONG_FIELD_TYPE
                raise e

    # Empty field
    encrypted_blob = None
    with pytest.raises(InspectionFailed):
        try:
            inspector.check_blob(encrypted_blob)

        except InspectionFailed as e:
            assert e.erno == errors.APPOINTMENT_EMPTY_FIELD
            raise e

    # Wrong format (no hex)
    encrypted_blobs = NO_HEX_STRINGS
    for encrypted_blob in encrypted_blobs:
        with pytest.raises(InspectionFailed):
            try:
                inspector.check_blob(encrypted_blob)

            except InspectionFailed as e:
                assert e.erno == errors.APPOINTMENT_WRONG_FIELD_FORMAT
                raise e


def test_inspect(run_bitcoind):
    # Valid appointment
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    start_time = block_processor.get_block_count() + 5
    end_time = start_time + 20
    to_self_delay = MIN_TO_SELF_DELAY
    encrypted_blob = get_random_value_hex(64)

    appointment_data = {
        "locator": locator,
        "start_time": start_time,
        "end_time": end_time,
        "to_self_delay": to_self_delay,
        "encrypted_blob": encrypted_blob,
    }

    appointment = inspector.inspect(appointment_data)

    assert (
        type(appointment) == Appointment
        and appointment.locator == locator
        and appointment.start_time == start_time
        and appointment.end_time == end_time
        and appointment.to_self_delay == to_self_delay
        and appointment.encrypted_blob == encrypted_blob
    )


def test_inspect_wrong(run_bitcoind):
    # Wrong types (taking out empty dict, since that's a different error)
    wrong_types = WRONG_TYPES.pop(WRONG_TYPES.index({}))
    for data in wrong_types:
        with pytest.raises(InspectionFailed):
            try:
                inspector.inspect(data)
            except InspectionFailed as e:
                print(data)
                assert e.erno == errors.APPOINTMENT_WRONG_FIELD
                raise e

    # None data
    with pytest.raises(InspectionFailed):
        try:
            inspector.inspect(None)
        except InspectionFailed as e:
            assert e.erno == errors.APPOINTMENT_EMPTY_FIELD
            raise e
