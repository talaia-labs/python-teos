from pisa import c_logger
from pisa.encrypted_blob import EncryptedBlob
from test.unit.conftest import get_random_value_hex

c_logger.disabled = True


def test_init_encrypted_blob():
    # No much to test here, basically that the object is properly created
    data = get_random_value_hex(64)
    assert (EncryptedBlob(data).data == data)


def test_decrypt():
    # TODO: The decryption tests are assuming the cipher is AES-GCM-128, since EncryptedBlob assumes the same. Fix this.
    key = get_random_value_hex(32)
    encrypted_data = get_random_value_hex(64)
    encrypted_blob = EncryptedBlob(encrypted_data)

    # Trying to decrypt random data (in AES_GCM-128) should result in an InvalidTag exception. Our decrypt function
    # returns None
    hex_tx = encrypted_blob.decrypt(key)
    assert hex_tx is None

    # Valid data should run with no InvalidTag and verify
    data = "6097cdf52309b1b2124efeed36bd34f46dc1c25ad23ac86f28380f746254f777"
    key = 'b2e984a570f6f49bc38ace178e09147b0aa296cbb7c92eb01412f7e2d07b5659'
    encrypted_data = "092e93d4a34aac4367075506f2c050ddfa1a201ee6669b65058572904dcea642aeb01ea4b57293618e8c46809dfadadc"
    encrypted_blob = EncryptedBlob(encrypted_data)

    assert(encrypted_blob.decrypt(key) == data)
