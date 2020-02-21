from binascii import unhexlify

from pisa.errors import *
from pisa.inspector import Inspector
from common.appointment import Appointment
from pisa.block_processor import BlockProcessor
from pisa.conf import MIN_TO_SELF_DELAY

from test.pisa.unit.conftest import get_random_value_hex, generate_dummy_appointment_data, generate_keypair, get_config

from common.constants import LOCATOR_LEN_BYTES, LOCATOR_LEN_HEX
from common.cryptographer import Cryptographer
from common.logger import Logger

from pisa import LOG_PREFIX
import common.cryptographer

common.cryptographer.logger = Logger(actor="Cryptographer", log_name_prefix=LOG_PREFIX)


inspector = Inspector(get_config())
APPOINTMENT_OK = (0, None)

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


def test_check_locator():
    # Right appointment type, size and format
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    assert Inspector.check_locator(locator) == APPOINTMENT_OK

    # Wrong size (too big)
    locator = get_random_value_hex(LOCATOR_LEN_BYTES + 1)
    assert Inspector.check_locator(locator)[0] == APPOINTMENT_WRONG_FIELD_SIZE

    # Wrong size (too small)
    locator = get_random_value_hex(LOCATOR_LEN_BYTES - 1)
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


def test_check_to_self_delay():
    # Right value, right format
    to_self_delays = [MIN_TO_SELF_DELAY, MIN_TO_SELF_DELAY + 1, MIN_TO_SELF_DELAY + 1000]
    for to_self_delay in to_self_delays:
        assert inspector.check_to_self_delay(to_self_delay) == APPOINTMENT_OK

    # to_self_delay too small
    to_self_delays = [MIN_TO_SELF_DELAY - 1, MIN_TO_SELF_DELAY - 2, 0, -1, -1000]
    for to_self_delay in to_self_delays:
        assert inspector.check_to_self_delay(to_self_delay)[0] == APPOINTMENT_FIELD_TOO_SMALL

    # Empty field
    to_self_delay = None
    assert inspector.check_to_self_delay(to_self_delay)[0] == APPOINTMENT_EMPTY_FIELD

    # Wrong data type
    to_self_delays = WRONG_TYPES
    for to_self_delay in to_self_delays:
        assert inspector.check_to_self_delay(to_self_delay)[0] == APPOINTMENT_WRONG_FIELD_TYPE


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


def test_check_appointment_signature():
    # The inspector receives the public key as hex
    client_sk, client_pk = generate_keypair()
    client_pk_hex = client_pk.format().hex()

    dummy_appointment_data, _ = generate_dummy_appointment_data(real_height=False)
    assert Inspector.check_appointment_signature(
        dummy_appointment_data["appointment"], dummy_appointment_data["signature"], dummy_appointment_data["public_key"]
    )

    fake_sk, _ = generate_keypair()

    # Create a bad signature to make sure inspector rejects it
    bad_signature = Cryptographer.sign(
        Appointment.from_dict(dummy_appointment_data["appointment"]).serialize(), fake_sk
    )
    assert (
        Inspector.check_appointment_signature(dummy_appointment_data["appointment"], bad_signature, client_pk_hex)[0]
        == APPOINTMENT_INVALID_SIGNATURE
    )


def test_inspect(run_bitcoind):
    # At this point every single check function has been already tested, let's test inspect with an invalid and a valid
    # appointments.

    client_sk, client_pk = generate_keypair()
    client_pk_hex = client_pk.format().hex()

    # Valid appointment
    locator = get_random_value_hex(LOCATOR_LEN_BYTES)
    start_time = BlockProcessor.get_block_count() + 5
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

    signature = Cryptographer.sign(Appointment.from_dict(appointment_data).serialize(), client_sk)

    appointment = inspector.inspect(appointment_data, signature, client_pk_hex)

    assert (
        type(appointment) == Appointment
        and appointment.locator == locator
        and appointment.start_time == start_time
        and appointment.end_time == end_time
        and appointment.to_self_delay == to_self_delay
        and appointment.encrypted_blob.data == encrypted_blob
    )
