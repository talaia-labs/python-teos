import hashlib
from binascii import hexlify
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SUPPORTED_HASH_FUNCTIONS = ['SHA256']
SUPPORTED_CYPHERS = ['AES-GCM-128']


class Blob:
    def __init__(self, data, cypher, hash_function):
        self.data = data
        self.cypher = cypher
        self.hash_function = hash_function

        # FIXME: We only support SHA256 for now
        if self.hash_function.upper() not in SUPPORTED_HASH_FUNCTIONS:
            raise Exception('Hash function not supported ({}). Supported Hash functions: {}'
                            .format(self.hash_function, SUPPORTED_HASH_FUNCTIONS))

        # FIXME: We only support SHA256 for now
        if self.cypher.upper() not in SUPPORTED_CYPHERS:
            raise Exception('Cypher not supported ({}). Supported cyphers: {}'.format(self.hash_function,
                                                                                      SUPPORTED_CYPHERS))

    def encrypt(self, tx_id):
        # Transaction to be encrypted
        # FIXME: The blob data should contain more things that just the transaction. Leaving like this for now.
        tx = self.data.encode()

        # FIXME: tx_id should not be necessary (can be derived from tx SegWit-like). Passing it for now
        # Extend the key using SHA256 as a KDF
        tx_id = tx_id.encode()
        extended_key = hashlib.sha256(tx_id[:16]).digest()

        # The 16 MSB of the extended key will serve as the AES GCM 128 secret key. The 16 LSB will serve as the IV.
        sk = extended_key[:16]
        nonce = extended_key[16:]

        # Encrypt the data
        aesgcm = AESGCM(sk)
        encrypted_blob = hexlify(aesgcm.encrypt(nonce=nonce, data=tx, associated_data=None)).decode()

        return encrypted_blob
