from hashlib import sha256
from binascii import unhexlify, hexlify
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from common.tools import check_sha256_hex_format

from pisa.logger import Logger

logger = Logger("Cryptographer")


class Cryptographer:
    @staticmethod
    def check_data_key_format(data, key):
        if len(data) % 2:
            error = "Incorrect (Odd-length) value."
            logger.error(error, data=data)
            raise ValueError(error)

        if not check_sha256_hex_format(key):
            error = "Key must be a 32-byte hex value (64 hex chars)."
            logger.error(error, key=key)
            raise ValueError(error)

        return True

    @staticmethod
    def encrypt(blob, key, rtype="hex"):
        if rtype not in ["hex", "bytes"]:
            raise ValueError("Wrong return type. Return type must be 'hex' or 'bytes'")

        Cryptographer.check_data_key_format(blob.data, key)

        # Transaction to be encrypted
        # FIXME: The blob data should contain more things that just the transaction. Leaving like this for now.
        tx = unhexlify(blob.data)

        # sk is the H(txid) (32-byte) and nonce is set to 0 (12-byte)
        sk = sha256(unhexlify(key)).digest()
        nonce = bytearray(12)

        logger.info("Encrypting blob.", sk=hexlify(sk).decode(), nonce=hexlify(nonce).decode(), blob=blob.data)

        # Encrypt the data
        cipher = ChaCha20Poly1305(sk)
        encrypted_blob = cipher.encrypt(nonce=nonce, data=tx, associated_data=None)

        if rtype == "hex":
            encrypted_blob = hexlify(encrypted_blob).decode("utf8")

        return encrypted_blob

    @staticmethod
    # ToDo: #20-test-tx-decrypting-edge-cases
    def decrypt(encrypted_blob, key, rtype="hex"):
        if rtype not in ["hex", "bytes"]:
            raise ValueError("Wrong return type. Return type must be 'hex' or 'bytes'")

        Cryptographer.check_data_key_format(encrypted_blob.data, key)

        # sk is the H(txid) (32-byte) and nonce is set to 0 (12-byte)
        sk = sha256(unhexlify(key)).digest()
        nonce = bytearray(12)

        logger.info(
            "Decrypting Blob.",
            sk=hexlify(sk).decode(),
            nonce=hexlify(nonce).decode(),
            encrypted_blob=encrypted_blob.data,
        )

        # Decrypt
        cipher = ChaCha20Poly1305(sk)
        data = unhexlify(encrypted_blob.data.encode())

        try:
            blob = cipher.decrypt(nonce=nonce, data=data, associated_data=None)

            # Change the blob encoding to hex depending on the rtype (default)
            if rtype == "hex":
                blob = hexlify(blob).decode("utf8")

        except InvalidTag:
            blob = None

        return blob
