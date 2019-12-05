import binascii

from common.cryptographer import Cryptographer
from pisa.encrypted_blob import EncryptedBlob
from test.unit.conftest import get_random_value_hex

data = "6097cdf52309b1b2124efeed36bd34f46dc1c25ad23ac86f28380f746254f777"
key = "b2e984a570f6f49bc38ace178e09147b0aa296cbb7c92eb01412f7e2d07b5659"
encrypted_data = "8f31028097a8bf12a92e088caab5cf3fcddf0d35ed2b72c24b12269373efcdea04f9d2a820adafe830c20ff132d89810"
encrypted_blob = EncryptedBlob(encrypted_data)


# TODO: The decryption tests are assuming the cipher is AES-GCM-128, since EncryptedBlob assumes the same. Fix this.
def test_decrypt_wrong_data():
    random_key = get_random_value_hex(32)
    random_encrypted_data = get_random_value_hex(64)
    random_encrypted_blob = EncryptedBlob(random_encrypted_data)

    # Trying to decrypt random data (in AES_GCM-128) should result in an InvalidTag exception. Our decrypt function
    # returns None
    hex_tx = Cryptographer.decrypt(random_encrypted_blob, random_key)
    assert hex_tx is None


def test_decrypt_odd_length():
    random_key = get_random_value_hex(32)
    random_encrypted_data_odd = get_random_value_hex(64)[:-1]
    random_encrypted_blob_odd = EncryptedBlob(random_encrypted_data_odd)

    assert Cryptographer.decrypt(random_encrypted_blob_odd, random_key) is None


def test_decrypt_hex():
    # Valid data should run with no InvalidTag and verify
    assert Cryptographer.decrypt(encrypted_blob, key) == data


def test_decrypt_bytes():
    # We can also get the decryption in bytes
    byte_blob = Cryptographer.decrypt(encrypted_blob, key, rtype="bytes")
    assert isinstance(byte_blob, bytes) and byte_blob == binascii.unhexlify(data)


def test_decrypt_wrong_return():
    # Any other type but "hex" (default) or "bytes" should fail
    try:
        Cryptographer.decrypt(encrypted_blob, key, rtype="random_value")
        assert False

    except ValueError:
        assert True


# def test_encrypt():
#     # Valid data, valid key
#     data = get_random_value_hex(64)
#     blob = Blob(data, SUPPORTED_CIPHERS[0], SUPPORTED_HASH_FUNCTIONS[0])
#     key = get_random_value_hex(32)
#
#     encrypted_blob = blob.encrypt(key)
#
#     # Invalid key (note that encrypt cannot be called with invalid data since that's checked when the Blob is created)
#     invalid_key = unhexlify(get_random_value_hex(32))
#
#     try:
#         blob.encrypt(invalid_key)
#         assert False, "Able to create encrypt with invalid key"
#
#     except ValueError:
#         assert True
#
#     # Check that two encryptions of the same data have the same result
#     encrypted_blob2 = blob.encrypt(key)
#
#     assert encrypted_blob == encrypted_blob2 and id(encrypted_blob) != id(encrypted_blob2)
