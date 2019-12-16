import binascii

from apps.cli.blob import Blob
from common.cryptographer import Cryptographer
from pisa.encrypted_blob import EncryptedBlob
from test.common.unit.conftest import get_random_value_hex

data = "6097cdf52309b1b2124efeed36bd34f46dc1c25ad23ac86f28380f746254f777"
key = "b2e984a570f6f49bc38ace178e09147b0aa296cbb7c92eb01412f7e2d07b5659"
encrypted_data = "8f31028097a8bf12a92e088caab5cf3fcddf0d35ed2b72c24b12269373efcdea04f9d2a820adafe830c20ff132d89810"


def test_check_data_key_format_wrong_data():
    data = get_random_value_hex(64)[:-1]
    key = get_random_value_hex(32)

    try:
        Cryptographer.check_data_key_format(data, key)
        assert False

    except ValueError as e:
        assert "Odd-length" in str(e)


def test_check_data_key_format_wrong_key():
    data = get_random_value_hex(64)
    key = get_random_value_hex(33)

    try:
        Cryptographer.check_data_key_format(data, key)
        assert False

    except ValueError as e:
        assert "32-byte hex" in str(e)


def test_check_data_key_format():
    data = get_random_value_hex(64)
    key = get_random_value_hex(32)

    assert Cryptographer.check_data_key_format(data, key) is True


def test_encrypt_odd_length_data():
    blob = Blob(get_random_value_hex(64)[-1])
    key = get_random_value_hex(32)

    try:
        Cryptographer.encrypt(blob, key)
        assert False

    except ValueError:
        assert True


def test_encrypt_wrong_key_size():
    blob = Blob(get_random_value_hex(64))
    key = get_random_value_hex(31)

    try:
        Cryptographer.encrypt(blob, key)
        assert False

    except ValueError:
        assert True


def test_encrypt_hex():
    blob = Blob(data)

    assert Cryptographer.encrypt(blob, key) == encrypted_data


def test_encrypt_bytes():
    blob = Blob(data)

    byte_blob = Cryptographer.encrypt(blob, key, rtype="bytes")
    assert isinstance(byte_blob, bytes) and byte_blob == binascii.unhexlify(encrypted_data)


def test_encrypt_wrong_return():
    # Any other type but "hex" (default) or "bytes" should fail
    try:
        Cryptographer.encrypt(Blob(data), key, rtype="random_value")
        assert False

    except ValueError:
        assert True


def test_decrypt_invalid_tag():
    random_key = get_random_value_hex(32)
    random_encrypted_data = get_random_value_hex(64)
    random_encrypted_blob = EncryptedBlob(random_encrypted_data)

    # Trying to decrypt random data should result in an InvalidTag exception. Our decrypt function
    # returns None
    hex_tx = Cryptographer.decrypt(random_encrypted_blob, random_key)
    assert hex_tx is None


def test_decrypt_odd_length_data():
    random_key = get_random_value_hex(32)
    random_encrypted_data_odd = get_random_value_hex(64)[:-1]
    random_encrypted_blob_odd = EncryptedBlob(random_encrypted_data_odd)

    try:
        Cryptographer.decrypt(random_encrypted_blob_odd, random_key)
        assert False

    except ValueError:
        assert True


def test_decrypt_wrong_key_size():
    random_key = get_random_value_hex(31)
    random_encrypted_data_odd = get_random_value_hex(64)
    random_encrypted_blob_odd = EncryptedBlob(random_encrypted_data_odd)

    try:
        Cryptographer.decrypt(random_encrypted_blob_odd, random_key)
        assert False

    except ValueError:
        assert True


def test_decrypt_hex():
    # Valid data should run with no InvalidTag and verify
    assert Cryptographer.decrypt(EncryptedBlob(encrypted_data), key) == data


def test_decrypt_bytes():
    # We can also get the decryption in bytes
    byte_blob = Cryptographer.decrypt(EncryptedBlob(encrypted_data), key, rtype="bytes")
    assert isinstance(byte_blob, bytes) and byte_blob == binascii.unhexlify(data)


def test_decrypt_wrong_return():
    # Any other type but "hex" (default) or "bytes" should fail
    try:
        Cryptographer.decrypt(EncryptedBlob(encrypted_data), key, rtype="random_value")
        assert False

    except ValueError:
        assert True
