from hashlib import sha256
from binascii import unhexlify, hexlify
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptedBlob:
    def __init__(self, data):
        self.data = data

    def decrypt(self, key, debug, logging):
        # master_key = H(tx_id | tx_id)
        master_key = sha256(key + key).digest()

        # The 16 MSB of the master key will serve as the AES GCM 128 secret key. The 16 LSB will serve as the IV.
        sk = master_key[:16]
        nonce = master_key[16:]

        if debug:
            logging.info("[Watcher] creating new blob")
            logging.info("[Watcher] master key: {}".format(hexlify(master_key).decode()))
            logging.info("[Watcher] sk: {}".format(hexlify(sk).decode()))
            logging.info("[Watcher] nonce: {}".format(hexlify(nonce).decode()))
            logging.info("[Watcher] encrypted_blob: {}".format(self.data))

        # Decrypt
        aesgcm = AESGCM(sk)
        data = unhexlify(self.data.encode())
        raw_tx = aesgcm.decrypt(nonce=nonce, data=data, associated_data=None)

        return raw_tx
