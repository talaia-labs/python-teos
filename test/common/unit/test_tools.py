from common.tools import check_sha256_hex_format
from test.common.unit.conftest import get_random_value_hex


def test_check_sha256_hex_format():
    # Only 32-byte hex encoded strings should pass the test
    wrong_inputs = [None, str(), 213, 46.67, dict(), "A" * 63, "C" * 65, bytes(), get_random_value_hex(31)]
    for wtype in wrong_inputs:
        assert check_sha256_hex_format(wtype) is False

    for v in range(100):
        assert check_sha256_hex_format(get_random_value_hex(32)) is True
