import json
from hashlib import sha256
from binascii import unhexlify, hexlify

from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.serialization import load_der_public_key, load_der_private_key
from cryptography.exceptions import InvalidSignature
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

    # NOTCOVERED
    @staticmethod
    def signature_format(data):
        # FIXME: This is temporary serialization. A proper one is required. Data need to be unhexlified too (can't atm)
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    # Deserialize public key from der data.
    @staticmethod
    def load_public_key_der(pk_der):
        try:
            pk = load_der_public_key(pk_der, backend=default_backend())
            return pk

        except UnsupportedAlgorithm:
            logger.error("Could not deserialize the public key (unsupported algorithm).")

        except ValueError:
            logger.error("The provided data cannot be deserialized (wrong size or format)")

        except TypeError:
            logger.error("The provided data cannot be deserialized (wrong type)")

        return None

    # Deserialize private key from der data.
    @staticmethod
    def load_private_key_der(sk_der):
        try:
            sk = load_der_private_key(sk_der, None, backend=default_backend())
            return sk

        except UnsupportedAlgorithm:
            raise ValueError("Could not deserialize the private key (unsupported algorithm).")

    @staticmethod
    def sign(data, sk, rtype="hex"):
        if rtype not in ["hex", "bytes"]:
            raise ValueError("Wrong return type. Return type must be 'hex' or 'bytes'")

        if not isinstance(sk, ec.EllipticCurvePrivateKey):
            logger.error("Wrong public key.")
            return None

        else:
            signature = sk.sign(data, ec.ECDSA(hashes.SHA256()))

            if rtype == "hex":
                signature = hexlify(signature).decode("utf-8")

            return signature

    @staticmethod
    def verify(message, signature, pk):
        if not isinstance(pk, ec.EllipticCurvePublicKey):
            logger.error("Wrong public key.")
            return False

        if isinstance(signature, str):
            signature = unhexlify(signature.encode("utf-8"))

        try:
            pk.verify(signature, message, ec.ECDSA(hashes.SHA256()))

            return True

        except InvalidSignature:
            return False
