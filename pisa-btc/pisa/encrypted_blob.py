from binascii import unhexlify, hexlify
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from conf import SALT


class EncryptedBlob:
    def __init__(self, data):
        self.data = data

    def decrypt(self, key, debug, logging):
        # Extend the key using HKDF
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=SALT.encode(),
            info=None,
            backend=default_backend()
        )

        extended_key = hkdf.derive(key)

        # The 16 MSB of the extended key will serve as the AES GCM 128 secret key. The 16 LSB will serve as the IV.
        sk = extended_key[:16]
        nonce = extended_key[16:]

        if debug:
            logging.info("[Watcher] creating new blob")
            logging.info("[Watcher] master key: {}".format(hexlify(key).decode()))
            logging.info("[Watcher] sk: {}".format(hexlify(sk).decode()))
            logging.info("[Watcher] nonce: {}".format(hexlify(nonce).decode()))
            logging.info("[Watcher] encrypted_blob: {}".format(self.data))

        # Decrypt
        aesgcm = AESGCM(sk)
        data = unhexlify(self.data.encode())
        raw_tx = aesgcm.decrypt(nonce=nonce, data=data, associated_data=None)

        return raw_tx
