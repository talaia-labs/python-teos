import re
from hashlib import sha256
from binascii import hexlify, unhexlify
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apps.cli import logging
from apps.cli import SUPPORTED_HASH_FUNCTIONS, SUPPORTED_CIPHERS


class Blob:
    def __init__(self, data, cipher, hash_function):
        if type(data) is not str or re.search(r'^[0-9A-Fa-f]+$', data) is None:
            raise ValueError("Non-Hex character found in txid.")

        self.data = data
        self.cipher = cipher
        self.hash_function = hash_function

        # FIXME: We only support SHA256 for now
        if self.hash_function.upper() not in SUPPORTED_HASH_FUNCTIONS:
            raise ValueError("Hash function not supported ({}). Supported Hash functions: {}"
                             .format(self.hash_function, SUPPORTED_HASH_FUNCTIONS))

        # FIXME: We only support AES-GCM-128 for now
        if self.cipher.upper() not in SUPPORTED_CIPHERS:
            raise ValueError("Cipher not supported ({}). Supported ciphers: {}".format(self.hash_function,
                                                                                       SUPPORTED_CIPHERS))

    def encrypt(self, tx_id):
        if len(tx_id) != 64:
            raise ValueError("txid does not matches the expected size (32-byte / 64 hex chars).")

        elif re.search(r'^[0-9A-Fa-f]+$', tx_id) is None:
            raise ValueError("Non-Hex character found in txid.")

        # Transaction to be encrypted
        # FIXME: The blob data should contain more things that just the transaction. Leaving like this for now.
        tx = unhexlify(self.data)
        tx_id = unhexlify(tx_id)

        # master_key = H(tx_id | tx_id)
        master_key = sha256(tx_id + tx_id).digest()

        # The 16 MSB of the master key will serve as the AES GCM 128 secret key. The 16 LSB will serve as the IV.
        sk = master_key[:16]
        nonce = master_key[16:]

        # Encrypt the data
        aesgcm = AESGCM(sk)
        encrypted_blob = aesgcm.encrypt(nonce=nonce, data=tx, associated_data=None)
        encrypted_blob = hexlify(encrypted_blob).decode()

        logging.info("[Client] creating new blob")
        logging.info("[Client] master key: {}".format(hexlify(master_key).decode()))
        logging.info("[Client] sk: {}".format(hexlify(sk).decode()))
        logging.info("[Client] nonce: {}".format(hexlify(nonce).decode()))
        logging.info("[Client] encrypted_blob: {}".format(encrypted_blob))

        return encrypted_blob
