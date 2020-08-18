import os

from common.constants import LOCATOR_LEN_BYTES
from common.tools import (
    is_compressed_pk,
    is_256b_hex_str,
    is_locator,
    compute_locator,
    setup_data_folder,
    is_u4int,
    intify,
)
from test.common.unit.conftest import get_random_value_hex


def test_is_compressed_pk():
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
        assert is_compressed_pk(prefix + get_random_value_hex(32))

    # check_user_pk must only accept values that is not a 33-byte hex string
    for value in wrong_values:
        assert not is_compressed_pk(value)


def test_is_256b_hex_str():
    # Only 32-byte hex encoded strings should pass the test
    wrong_inputs = [None, str(), 213, 46.67, dict(), "A" * 63, "C" * 65, bytes(), get_random_value_hex(31)]
    for wtype in wrong_inputs:
        assert is_256b_hex_str(wtype) is False

    for v in range(100):
        assert is_256b_hex_str(get_random_value_hex(32)) is True


def test_is_u4int():
    out_of_range = [-1, pow(2, 32)]
    in_range = [0, pow(2, 32) // 2, pow(2, 32) - 1]
    wrong_inputs = [None, str(), 46.67, dict(), "A", bytes(), get_random_value_hex(31)]

    # Test ints out of the range return false
    for x in out_of_range:
        assert not is_u4int(x)

    # Same for wrong inputs
    for x in wrong_inputs:
        assert not is_u4int(x)

    # True is returned for values in range
    for x in in_range:
        assert is_u4int(x)


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
        assert is_locator(wtype) is False

    for _ in range(100):
        assert is_locator(get_random_value_hex(LOCATOR_LEN_BYTES)) is True


def test_compute_locator():
    # The best way of checking that compute locator is correct is by using is_locator
    for _ in range(100):
        assert is_locator(compute_locator(get_random_value_hex(LOCATOR_LEN_BYTES))) is True

    # String of length smaller than LOCATOR_LEN_BYTES bytes must fail
    for i in range(1, LOCATOR_LEN_BYTES):
        assert is_locator(compute_locator(get_random_value_hex(i))) is False


def test_setup_data_folder():
    # This method should create a folder if it does not exist, and do nothing otherwise
    test_folder = "test_folder"
    assert not os.path.isdir(test_folder)

    setup_data_folder(test_folder)

    assert os.path.isdir(test_folder)

    os.rmdir(test_folder)


def test_intify_unchanged():
    test_cases = [
        0,
        1.1,
        True,
        False,
        "yo",
        {},
        [],
    ]
    for x in test_cases:
        assert intify(x) == x

    res = intify([3, 2.5, "yo"])
    assert res == [3, 2.5, "yo"]
    assert type(res[0]) == int
    assert type(res[1]) == float

    x = [3, 2.5, "yo", [4]]
    res = intify(x)
    assert res == x
    assert type(res[0]) == int
    assert type(res[1]) == float
    assert type(res[3][0]) == int

    x = {"a": 1, "b": 2.5, "c": {"d": [8]}}
    res = intify(x)
    assert res == x
    assert type(res["a"] == int)
    assert type(res["b"] == float)
    assert type(res["c"]["d"][0] == int)


def test_intify_changed():
    assert intify(1.0) == 1
    assert intify(-1.0) == -1

    x = [1.0, 1.5, -2.0, True]
    res = intify(x)
    assert res == [1, 1.5, -2, True]
    assert type(res[0]) == int
    assert type(res[1]) == float
    assert type(res[2]) == int
    assert type(res[3]) == bool

    x = {"a": 1.0, "b": 1.5, "c": -2.0, "d": False}
    res = intify(x)
    assert res == {"a": 1, "b": 1.5, "c": -2, "d": False}
    assert type(res["a"]) == int
    assert type(res["b"]) == float
    assert type(res["c"]) == int
    assert type(res["d"]) == bool

    x = {"a": 1.0, "b": [4, {"c": 5.0, "cc": 5.5}], "d": {"e": ["foo", 6, 6.5, 7.0]}}
    res = intify(x)
    assert res == {"a": 1, "b": [4, {"c": 5, "cc": 5.5}], "d": {"e": ["foo", 6, 6.5, 7]}}
    assert type(res["a"]) == int
    assert type(res["b"][0]) == int
    assert type(res["b"][1]["c"]) == int
    assert type(res["b"][1]["cc"]) == float
    assert type(res["d"]["e"][1]) == int
    assert type(res["d"]["e"][2]) == float
    assert type(res["d"]["e"][3]) == int
