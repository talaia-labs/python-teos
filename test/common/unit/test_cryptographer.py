import os
from binascii import unhexlify
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from coincurve import PrivateKey, PublicKey
import common.cryptographer
from common.logger import Logger
from common.cryptographer import Cryptographer
from test.common.unit.conftest import get_random_value_hex

common.cryptographer.logger = Logger(actor="Cryptographer", log_name_prefix="")

data = "6097cdf52309b1b2124efeed36bd34f46dc1c25ad23ac86f28380f746254f777"
key = "b2e984a570f6f49bc38ace178e09147b0aa296cbb7c92eb01412f7e2d07b5659"
encrypted_data = "8f31028097a8bf12a92e088caab5cf3fcddf0d35ed2b72c24b12269373efcdea04f9d2a820adafe830c20ff132d89810"


WRONG_TYPES = [None, 2134, 14.56, str(), list(), dict()]


def generate_keypair():
    sk = PrivateKey()
    pk = sk.public_key

    return sk, pk


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
    blob = get_random_value_hex(64)[-1]
    key = get_random_value_hex(32)

    try:
        Cryptographer.encrypt(blob, key)
        assert False

    except ValueError:
        assert True


def test_encrypt_wrong_key_size():
    blob = get_random_value_hex(64)
    key = get_random_value_hex(31)

    try:
        Cryptographer.encrypt(blob, key)
        assert False

    except ValueError:
        assert True


def test_encrypt():
    assert Cryptographer.encrypt(data, key) == encrypted_data


def test_decrypt_invalid_tag():
    random_key = get_random_value_hex(32)
    random_encrypted_data = get_random_value_hex(64)
    random_encrypted_blob = random_encrypted_data

    # Trying to decrypt random data should result in an InvalidTag exception. Our decrypt function
    # returns None
    hex_tx = Cryptographer.decrypt(random_encrypted_blob, random_key)
    assert hex_tx is None


def test_decrypt_odd_length_data():
    random_key = get_random_value_hex(32)
    random_encrypted_data_odd = get_random_value_hex(64)[:-1]
    random_encrypted_blob_odd = random_encrypted_data_odd

    try:
        Cryptographer.decrypt(random_encrypted_blob_odd, random_key)
        assert False

    except ValueError:
        assert True


def test_decrypt_wrong_key_size():
    random_key = get_random_value_hex(31)
    random_encrypted_data_odd = get_random_value_hex(64)
    random_encrypted_blob_odd = random_encrypted_data_odd

    try:
        Cryptographer.decrypt(random_encrypted_blob_odd, random_key)
        assert False

    except ValueError:
        assert True


def test_decrypt():
    # Valid data should run with no InvalidTag and verify
    assert Cryptographer.decrypt(encrypted_data, key) == data


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


def test_load_private_key_der():
    # load_private_key_der expects a byte encoded data. Any other should fail and return None
    for wtype in WRONG_TYPES:
        assert Cryptographer.load_private_key_der(wtype) is None

    # On the other hand, any random formatter byte array would also fail (zeros for example)
    assert Cryptographer.load_private_key_der(bytes(32)) is None

    # A proper formatted key should load
    sk_der = generate_keypair()[0].to_der()
    assert Cryptographer.load_private_key_der(sk_der) is not None


def test_sign():
    # Otherwise we should get a signature
    sk, _ = generate_keypair()
    message = b""

    assert Cryptographer.sign(message, sk) is not None
    assert isinstance(Cryptographer.sign(message, sk), str)


def test_sign_ground_truth():
    # Generate a signature that has been verified by c-lightning.
    raw_sk = "24e9a981580d27d9277071a8381542e89a7c124868c4e862a13595dc75c6922f"
    sk = PrivateKey.from_hex(raw_sk)

    c_lightning_rpk = "0235293db86c6aaa74aff69ebacad8471d5242901ea9f6a0341a8dca331875e62c"
    message = b"Test message"

    sig = Cryptographer.sign(message, sk)
    rpk = Cryptographer.recover_pk(message, sig)

    assert Cryptographer.verify_rpk(PublicKey(unhexlify(c_lightning_rpk)), rpk)


def test_sign_wrong_sk():
    # If a sk is not passed, sign will return None
    for wtype in WRONG_TYPES:
        assert Cryptographer.sign(b"", wtype) is None


def test_recover_pk():
    sk, _ = generate_keypair()
    message = b"Test message"

    zbase32_sig = Cryptographer.sign(message, sk)
    rpk = Cryptographer.recover_pk(message, zbase32_sig)

    assert isinstance(rpk, PublicKey)


def test_recover_pk_invalid_sigrec():
    message = "Hey, it's me"
    signature = "ddbfb019e4d56155b4175066c2b615ab765d317ae7996d188b4a5fae4cc394adf98fef46034d0553149392219ca6d37dca9abdfa6366a8e54b28f19d3e5efa8a14b556205dc7f33a"

    # The given signature, when zbase32 decoded, has a fist byte with value lower than 31.
    # The first byte of the signature should be 31 + SigRec, so this should fail
    assert Cryptographer.recover_pk(message, signature) is None


def test_recover_pk_ground_truth():
    # Use a message a signature generated by c-lightning and see if we recover the proper key
    message = b"Test message"
    org_pk = "02b821c749295d5c24f6166ae77d8353eaa36fc4e47326670c6d2522cbd344bab9"
    zsig = "rbwewwyr4zem3w5t39fd1xyeamfzbmfgztwm4b613ybjtmoeod5kazaxqo3akn3ae75bqi3aqeds8cs6n43w4p58ft34itjnnb61bp54"

    rpk = Cryptographer.recover_pk(message, zsig)

    assert Cryptographer.verify_rpk(PublicKey(unhexlify(org_pk)), rpk)


def test_recover_pk_wrong_inputs():
    str_message = "Test message"
    message = bytes(20)
    str_sig = "aaaaaaaa"
    sig = bytes(20)

    # Wrong input type
    assert Cryptographer.recover_pk(message, str_sig) is None
    assert Cryptographer.recover_pk(str_message, str_sig) is None
    assert Cryptographer.recover_pk(str_message, sig) is None
    assert Cryptographer.recover_pk(message, str_sig) is None

    # Wrong input size or format
    assert Cryptographer.recover_pk(message, sig) is None
    assert Cryptographer.recover_pk(message, bytes(104)) is None


def test_verify_pk():
    sk, _ = generate_keypair()
    message = b"Test message"

    zbase32_sig = Cryptographer.sign(message, sk)
    rpk = Cryptographer.recover_pk(message, zbase32_sig)

    assert Cryptographer.verify_rpk(sk.public_key, rpk)


def test_verify_pk_wrong():
    sk, _ = generate_keypair()
    sk2, _ = generate_keypair()
    message = b"Test message"

    zbase32_sig = Cryptographer.sign(message, sk)
    rpk = Cryptographer.recover_pk(message, zbase32_sig)

    assert not Cryptographer.verify_rpk(sk2.public_key, rpk)


def test_get_compressed_pk():
    sk, pk = generate_keypair()
    compressed_pk = Cryptographer.get_compressed_pk(pk)

    assert isinstance(compressed_pk, str) and len(compressed_pk) == 66
    assert compressed_pk[:2] in ["02", "03"]


def test_get_compressed_pk_wrong_key():
    # pk should be properly initialized. Initializing from int will case it to not be recoverable
    pk = PublicKey(0)
    compressed_pk = Cryptographer.get_compressed_pk(pk)

    assert compressed_pk is None


def test_get_compressed_pk_wrong_type():
    # Passing a value that is not a PublicKey will make it to fail too
    pk = get_random_value_hex(33)
    compressed_pk = Cryptographer.get_compressed_pk(pk)

    assert compressed_pk is None
