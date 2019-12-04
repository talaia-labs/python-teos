import re
from hashlib import sha256
from binascii import hexlify, unhexlify
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from apps.cli import logger


class Blob:
    def __init__(self, data):
        if type(data) is not str or re.search(r"^[0-9A-Fa-f]+$", data) is None:
            raise ValueError("Non-Hex character found in txid.")

        self.data = data

    def encrypt(self, tx_id):
        if len(tx_id) != 64:
            raise ValueError("txid does not matches the expected size (32-byte / 64 hex chars).")

        elif re.search(r"^[0-9A-Fa-f]+$", tx_id) is None:
            raise ValueError("Non-Hex character found in txid.")

        # Transaction to be encrypted
        # FIXME: The blob data should contain more things that just the transaction. Leaving like this for now.
        tx = unhexlify(self.data)

        # sk is the H(txid) (32-byte) and nonce is set to 0 (12-byte)
        sk = sha256(unhexlify(tx_id)).digest()
        nonce = bytearray(12)

        # Encrypt the data
        cipher = ChaCha20Poly1305(sk)
        encrypted_blob = cipher.encrypt(nonce=nonce, data=tx, associated_data=None)
        encrypted_blob = hexlify(encrypted_blob).decode()

        logger.info(
            "Creating new blob", sk=hexlify(sk).decode(), nonce=hexlify(nonce).decode(), encrypted_blob=encrypted_blob
        )

        return encrypted_blob
