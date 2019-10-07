from os import urandom
from cryptography.exceptions import InvalidTag

from pisa import logging
from pisa.encrypted_blob import EncryptedBlob


def test_init_encrypted_blob():
    # No much to test here, basically that the object is properly created
    data = urandom(64).hex()
    assert (EncryptedBlob(data).data == data)


def test_decrypt():
    # TODO: The decryption tests are assuming the cipher is AES-GCM-128, since EncryptedBlob assumes the same. Fix this.
    key = urandom(32).hex()
    encrypted_data = urandom(64).hex()
    encrypted_blob = EncryptedBlob(encrypted_data)

    # Trying to decrypt random data (in AES_GCM-128) should result in an InvalidTag exception
    try:
        encrypted_blob.decrypt(key)
        assert False, "Able to decrypt random data with random key"

    except InvalidTag:
        assert True

    # Valid data should run with no InvalidTag and verify
    data = "6097cdf52309b1b2124efeed36bd34f46dc1c25ad23ac86f28380f746254f777"
    key = 'b2e984a570f6f49bc38ace178e09147b0aa296cbb7c92eb01412f7e2d07b5659'
    encrypted_data = "092e93d4a34aac4367075506f2c050ddfa1a201ee6669b65058572904dcea642aeb01ea4b57293618e8c46809dfadadc"
    encrypted_blob = EncryptedBlob(encrypted_data)

    assert(encrypted_blob.decrypt(key) == data)


logging.getLogger().disabled = True

test_init_encrypted_blob()
test_decrypt()

