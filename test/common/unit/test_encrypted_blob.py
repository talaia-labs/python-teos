from common.encrypted_blob import EncryptedBlob
from test.common.unit.conftest import get_random_value_hex


def test_init_encrypted_blob():
    # No much to test here, basically that the object is properly created
    data = get_random_value_hex(64)
    assert EncryptedBlob(data).data == data


def test_equal():
    data = get_random_value_hex(64)
    e_blob1 = EncryptedBlob(data)
    e_blob2 = EncryptedBlob(data)

    assert e_blob1 == e_blob2 and id(e_blob1) != id(e_blob2)
