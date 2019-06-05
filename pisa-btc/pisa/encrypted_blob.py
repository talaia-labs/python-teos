import hashlib
from binascii import unhexlify
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptedBlob:
    def __init__(self, data):
        self.data = data

    def decrypt(self, key):
        # Extend the key using SHA256 as a KDF
        extended_key = hashlib.sha256(key).digest()

        # The 16 MSB of the extended key will serve as the AES GCM 128 secret key. The 16 LSB will serve as the IV.
        sk = extended_key[:16]
        nonce = extended_key[16:]

        # Decrypt
        aesgcm = AESGCM(sk)
        data = unhexlify(self.data.encode)
        raw_tx = aesgcm.decrypt(nonce=nonce, data=data, associated_data=None)

        return raw_tx
