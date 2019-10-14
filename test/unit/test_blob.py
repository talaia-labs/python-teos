from os import urandom

from pisa import logging
from apps.cli.blob import Blob
from pisa.conf import SUPPORTED_CIPHERS, SUPPORTED_HASH_FUNCTIONS

logging.getLogger().disabled = True


def test_init_blob():
    data = urandom(64).hex()

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
    data = urandom(64)
    cipher = SUPPORTED_CIPHERS[0]
    hash_function = SUPPORTED_HASH_FUNCTIONS[0]

    try:
        Blob(data, cipher, hash_function)
        assert False, "Able to create blob with wrong data"

    except ValueError:
        assert True

    # Invalid cipher
    data = urandom(64).hex()
    cipher = "A" * 10
    hash_function = SUPPORTED_HASH_FUNCTIONS[0]

    try:
        Blob(data, cipher, hash_function)
        assert False, "Able to create blob with wrong data"

    except ValueError:
        assert True

    # Invalid hash function
    data = urandom(64).hex()
    cipher = SUPPORTED_CIPHERS[0]
    hash_function = "A" * 10

    try:
        Blob(data, cipher, hash_function)
        assert False, "Able to create blob with wrong data"

    except ValueError:
        assert True


def test_encrypt():
    # Valid data, valid key
    data = urandom(64).hex()
    blob = Blob(data, SUPPORTED_CIPHERS[0], SUPPORTED_HASH_FUNCTIONS[0])
    key = urandom(32).hex()

    encrypted_blob = blob.encrypt(key)

    # Invalid key (note that encrypt cannot be called with invalid data since that's checked when the Blob is created)
    invalid_key = urandom(32)

    try:
        blob.encrypt(invalid_key)
        assert False, "Able to create encrypt with invalid key"

    except ValueError:
        assert True

    # Check that two encryptions of the same data have the same result
    encrypted_blob2 = blob.encrypt(key)

    assert(encrypted_blob == encrypted_blob2 and id(encrypted_blob) != id(encrypted_blob2))
