from binascii import unhexlify

from common.blob import Blob
from test.common.unit.conftest import get_random_value_hex


def test_init_blob():
    data = get_random_value_hex(64)
    blob = Blob(data)
    assert isinstance(blob, Blob)

    # Wrong data
    try:
        Blob(unhexlify(get_random_value_hex(64)))
        assert False, "Able to create blob with wrong data"

    except ValueError:
        assert True
