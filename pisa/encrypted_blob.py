from hashlib import sha256
from binascii import unhexlify, hexlify
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pisa import Logger

logger = Logger("Watcher")


# FIXME: EncryptedBlob is assuming AES-128-GCM. A cipher field should be part of the object and the decryption should be
#        performed depending on the cipher.
class EncryptedBlob:
    def __init__(self, data):
        self.data = data

    def __eq__(self, other):
        return isinstance(other, EncryptedBlob) and self.data == other.data

    def decrypt(self, key):
        # master_key = H(tx_id | tx_id)
        key = unhexlify(key)
        master_key = sha256(key + key).digest()

        # The 16 MSB of the master key will serve as the AES GCM 128 secret key. The 16 LSB will serve as the IV.
        sk = master_key[:16]
        nonce = master_key[16:]

        logger.info("[Watcher] creating new blob.",
                    master_key=hexlify(master_key).decode(),
                    sk=hexlify(sk).decode(),
                    nonce=hexlify(sk).decode(),
                    encrypted_blob=self.data)

        # Decrypt
        aesgcm = AESGCM(sk)
        data = unhexlify(self.data.encode())
        raw_tx = aesgcm.decrypt(nonce=nonce, data=data, associated_data=None)
        hex_raw_tx = hexlify(raw_tx).decode('utf8')

        return hex_raw_tx
