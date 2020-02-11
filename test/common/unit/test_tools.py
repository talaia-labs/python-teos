import os
import pytest
import logging
from copy import deepcopy

from pisa import conf_fields

from common.constants import LOCATOR_LEN_BYTES
from common.tools import (
    check_sha256_hex_format,
    check_locator_format,
    compute_locator,
    setup_data_folder,
    check_conf_fields,
    extend_paths,
    setup_logging,
)
from test.common.unit.conftest import get_random_value_hex


conf_fields_copy = deepcopy(conf_fields)


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
        assert check_sha256_hex_format(wtype) is False

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


def test_check_conf_fields():
    # The test should work with a valid config_fields (obtained from a valid conf.py)
    assert type(check_conf_fields(conf_fields_copy)) == dict


def test_bad_check_conf_fields():
    # Create a messed up version of the file that should throw an error.
    conf_fields_copy["BTC_RPC_USER"] = 0000
    conf_fields_copy["BTC_RPC_PASSWD"] = "password"
    conf_fields_copy["BTC_RPC_HOST"] = 000

    # We should get a ValueError here.
    with pytest.raises(Exception):
        check_conf_fields(conf_fields_copy)


def test_extend_paths():
    # Test that only items with the path flag are extended
    config_fields = {
        "foo": {"value": "foofoo"},
        "var": {"value": "varvar", "path": True},
        "foovar": {"value": "foovarfoovar"},
    }
    base_path = "base_path/"
    extended_config_field = extend_paths(base_path, config_fields)

    for k, field in extended_config_field.items():
        if field.get("path") is True:
            assert base_path in field.get("value")
        else:
            assert base_path not in field.get("value")


def test_setup_logging():
    # Check that setup_logging creates two new logs for every prefix
    prefix = "foo"
    log_file = "var.log"

    f_log_suffix = "_file_log"
    c_log_suffix = "_console_log"

    assert len(logging.getLogger(prefix + f_log_suffix).handlers) is 0
    assert len(logging.getLogger(prefix + c_log_suffix).handlers) is 0

    setup_logging(log_file, prefix)

    assert len(logging.getLogger(prefix + f_log_suffix).handlers) is 1
    assert len(logging.getLogger(prefix + c_log_suffix).handlers) is 1

    os.remove(log_file)
