import os
import logging

from common.constants import LOCATOR_LEN_BYTES
from common.tools import (
    check_compressed_pk_format,
    check_sha256_hex_format,
    check_locator_format,
    compute_locator,
    setup_data_folder,
    setup_logging,
)
from test.common.unit.conftest import get_random_value_hex


def test_check_compressed_pk_format():
    wrong_values = [
        None,
        3,
        15.23,
        "",
        {},
        (),
        object,
        str,
        get_random_value_hex(32),
        get_random_value_hex(34),
        "06" + get_random_value_hex(32),
    ]

    # check_user_pk must only accept values that is not a 33-byte hex string
    for i in range(100):
        if i % 2:
            prefix = "02"
        else:
            prefix = "03"
        assert check_compressed_pk_format(prefix + get_random_value_hex(32))

    # check_user_pk must only accept values that is not a 33-byte hex string
    for value in wrong_values:
        assert not check_compressed_pk_format(value)


def test_check_sha256_hex_format():
    # Only 32-byte hex encoded strings should pass the test
    wrong_inputs = [None, str(), 213, 46.67, dict(), "A" * 63, "C" * 65, bytes(), get_random_value_hex(31)]
    for wtype in wrong_inputs:
        assert check_sha256_hex_format(wtype) is False

    for v in range(100):
        assert check_sha256_hex_format(get_random_value_hex(32)) is True


def test_check_locator_format():
    # Check that only LOCATOR_LEN_BYTES long string pass the test

    wrong_inputs = [
        None,
        str(),
        213,
        46.67,
        dict(),
        "A" * (2 * LOCATOR_LEN_BYTES - 1),
        "C" * (2 * LOCATOR_LEN_BYTES + 1),
        bytes(),
        get_random_value_hex(LOCATOR_LEN_BYTES - 1),
    ]
    for wtype in wrong_inputs:
        assert check_locator_format(wtype) is False

    for _ in range(100):
        assert check_locator_format(get_random_value_hex(LOCATOR_LEN_BYTES)) is True


def test_compute_locator():
    # The best way of checking that compute locator is correct is by using check_locator_format
    for _ in range(100):
        assert check_locator_format(compute_locator(get_random_value_hex(LOCATOR_LEN_BYTES))) is True

    # String of length smaller than LOCATOR_LEN_BYTES bytes must fail
    for i in range(1, LOCATOR_LEN_BYTES):
        assert check_locator_format(compute_locator(get_random_value_hex(i))) is False


def test_setup_data_folder():
    # This method should create a folder if it does not exist, and do nothing otherwise
    test_folder = "test_folder"
    assert not os.path.isdir(test_folder)

    setup_data_folder(test_folder)

    assert os.path.isdir(test_folder)

    os.rmdir(test_folder)


def test_setup_logging():
    # Check that setup_logging creates two new logs for every prefix
    prefix = "foo"
    log_file = "var.log"

    f_log_suffix = "_file_log"
    c_log_suffix = "_console_log"

    assert len(logging.getLogger(prefix + f_log_suffix).handlers) == 0
    assert len(logging.getLogger(prefix + c_log_suffix).handlers) == 0

    setup_logging(log_file, prefix)

    assert len(logging.getLogger(prefix + f_log_suffix).handlers) == 1
    assert len(logging.getLogger(prefix + c_log_suffix).handlers) == 1

    os.remove(log_file)
