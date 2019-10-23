from binascii import unhexlify

from pisa import logging
from apps.cli.blob import Blob
from test.unit.conftest import get_random_value_hex
from pisa.conf import SUPPORTED_CIPHERS, SUPPORTED_HASH_FUNCTIONS

logging.getLogger().disabled = True


def test_init_blob():
    data = get_random_value_hex(64)

    # Fixed (valid) hash function, try different valid ciphers
    hash_function = SUPPORTED_HASH_FUNCTIONS[0]
    for cipher in SUPPORTED_CIPHERS:
        cipher_cases = [cipher, cipher.lower(), cipher.capitalize()]

        for case in cipher_cases:
            blob = Blob(data, case, hash_function)
            assert(blob.data == data and blob.cipher == case and blob.hash_function == hash_function)

    # Fixed (valid) cipher, try different valid hash functions
    cipher = SUPPORTED_CIPHERS[0]
    for hash_function in SUPPORTED_HASH_FUNCTIONS:
        hash_function_cases = [hash_function, hash_function.lower(), hash_function.capitalize()]

        for case in hash_function_cases:
            blob = Blob(data, cipher, case)
            assert(blob.data == data and blob.cipher == cipher and blob.hash_function == case)

    # Invalid data
    data = unhexlify(get_random_value_hex(64))
    cipher = SUPPORTED_CIPHERS[0]
    hash_function = SUPPORTED_HASH_FUNCTIONS[0]

    try:
        Blob(data, cipher, hash_function)
        assert False, "Able to create blob with wrong data"

    except ValueError:
        assert True

    # Invalid cipher
    data = get_random_value_hex(64)
    cipher = "A" * 10
    hash_function = SUPPORTED_HASH_FUNCTIONS[0]

    try:
        Blob(data, cipher, hash_function)
        assert False, "Able to create blob with wrong data"

    except ValueError:
        assert True

    # Invalid hash function
    data = get_random_value_hex(64)
    cipher = SUPPORTED_CIPHERS[0]
    hash_function = "A" * 10

    try:
        Blob(data, cipher, hash_function)
        assert False, "Able to create blob with wrong data"

    except ValueError:
        assert True


def test_encrypt():
    # Valid data, valid key
    data = get_random_value_hex(64)
    blob = Blob(data, SUPPORTED_CIPHERS[0], SUPPORTED_HASH_FUNCTIONS[0])
    key = get_random_value_hex(32)

    encrypted_blob = blob.encrypt(key)

    # Invalid key (note that encrypt cannot be called with invalid data since that's checked when the Blob is created)
    invalid_key = unhexlify(get_random_value_hex(32))

    try:
        blob.encrypt(invalid_key)
        assert False, "Able to create encrypt with invalid key"

    except ValueError:
        assert True

    # Check that two encryptions of the same data have the same result
    encrypted_blob2 = blob.encrypt(key)

    assert(encrypted_blob == encrypted_blob2 and id(encrypted_blob) != id(encrypted_blob2))
