import os
import binascii
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

import common.cryptographer
from common.blob import Blob
from common.logger import Logger
from common.cryptographer import Cryptographer
from common.encrypted_blob import EncryptedBlob
from test.common.unit.conftest import get_random_value_hex

common.cryptographer.logger = Logger(actor="Cryptographer", log_name_prefix="")

data = "6097cdf52309b1b2124efeed36bd34f46dc1c25ad23ac86f28380f746254f777"
key = "b2e984a570f6f49bc38ace178e09147b0aa296cbb7c92eb01412f7e2d07b5659"
encrypted_data = "8f31028097a8bf12a92e088caab5cf3fcddf0d35ed2b72c24b12269373efcdea04f9d2a820adafe830c20ff132d89810"


WRONG_TYPES = [None, 2134, 14.56, str(), list(), dict()]


def generate_keypair():
    sk = ec.generate_private_key(ec.SECP256K1, default_backend())
    pk = sk.public_key()

    sk_der = sk.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    return sk, pk


def generate_keypair_der():
    sk, pk = generate_keypair()

    sk_der = sk.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    pk_der = pk.public_bytes(
        encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return sk_der, pk_der


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


def test_load_key_file():
    dummy_sk = ec.generate_private_key(ec.SECP256K1, default_backend())
    dummy_sk_der = dummy_sk.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # If file exists and has data in it, function should work.
    with open("key_test_file", "wb") as f:
        f.write(dummy_sk_der)

    appt_data = Cryptographer.load_key_file("key_test_file")
    assert appt_data

    os.remove("key_test_file")

    # If file doesn't exist, function should return None
    assert Cryptographer.load_key_file("nonexistent_file") is None

    # If something that's not a file_path is passed as parameter the method should also return None
    assert Cryptographer.load_key_file(0) is None and Cryptographer.load_key_file(None) is None


def test_load_public_key_der():
    # load_public_key_der expects a byte encoded data. Any other should fail and return None
    for wtype in WRONG_TYPES:
        assert Cryptographer.load_public_key_der(wtype) is None

    # On the other hand, any random formatter byte array would also fail (zeros for example)
    assert Cryptographer.load_public_key_der(bytes(32)) is None

    # A proper formatted key should load
    _, pk_der = generate_keypair_der()
    assert Cryptographer.load_public_key_der(pk_der) is not None


def test_load_private_key_der():
    # load_private_key_der expects a byte encoded data. Any other should fail and return None
    for wtype in WRONG_TYPES:
        assert Cryptographer.load_private_key_der(wtype) is None

    # On the other hand, any random formatter byte array would also fail (zeros for example)
    assert Cryptographer.load_private_key_der(bytes(32)) is None

    # A proper formatted key should load
    sk_der, _ = generate_keypair_der()
    assert Cryptographer.load_private_key_der(sk_der) is not None


def test_sign_wrong_rtype():
    # Calling sign with an rtype different than 'str' or 'bytes' should fail
    for wtype in WRONG_TYPES:
        try:
            Cryptographer.sign(b"", "", rtype=wtype)
            assert False

        except ValueError:
            assert True


def test_sign_wrong_sk():
    # If a sk is not passed, sign will return None
    for wtype in WRONG_TYPES:
        assert Cryptographer.sign(b"", wtype) is None


def test_sign():
    # Otherwise we should get a signature
    sk, _ = generate_keypair()
    message = b""

    assert Cryptographer.sign(message, sk) is not None

    # Check that the returns work
    assert isinstance(Cryptographer.sign(message, sk, rtype="str"), str)
    assert isinstance(Cryptographer.sign(message, sk, rtype="bytes"), bytes)


def test_verify_wrong_pk():
    # If a pk is not passed, verify will return None
    for wtype in WRONG_TYPES:
        assert Cryptographer.sign("", wtype) is None


def test_verify_random_values():
    # Random values shouldn't verify
    sk, pk = generate_keypair()

    message = binascii.unhexlify(get_random_value_hex(32))
    signature = get_random_value_hex(32)

    assert Cryptographer.verify(message, signature, pk) is False


def test_verify_wrong_pair():
    # Verifying with a wrong keypair must fail
    sk, _ = generate_keypair()
    _, pk = generate_keypair()

    message = binascii.unhexlify(get_random_value_hex(32))
    signature = get_random_value_hex(32)

    assert Cryptographer.verify(message, signature, pk) is False


def test_verify_wrong_message():
    # Verifying with a wrong keypair must fail
    sk, pk = generate_keypair()

    message = binascii.unhexlify(get_random_value_hex(32))
    signature = Cryptographer.sign(message, sk)

    wrong_message = binascii.unhexlify(get_random_value_hex(32))

    assert Cryptographer.verify(wrong_message, signature, pk) is False


def test_verify():
    # A properly generated signature should verify
    sk, pk = generate_keypair()
    message = binascii.unhexlify(get_random_value_hex(32))
    signature = Cryptographer.sign(message, sk)

    assert Cryptographer.verify(message, signature, pk) is True
