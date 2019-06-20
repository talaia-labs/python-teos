from binascii import hexlify, unhexlify
from hashlib import sha256
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from conf import SUPPORTED_HASH_FUNCTIONS, SUPPORTED_CIPHERS


class Blob:
    def __init__(self, data, cypher, hash_function):
        self.data = data
        self.cypher = cypher
        self.hash_function = hash_function

        # FIXME: We only support SHA256 for now
        if self.hash_function.upper() not in SUPPORTED_HASH_FUNCTIONS:
            raise Exception("Hash function not supported ({}). Supported Hash functions: {}"
                            .format(self.hash_function, SUPPORTED_HASH_FUNCTIONS))

        # FIXME: We only support SHA256 for now
        if self.cypher.upper() not in SUPPORTED_CIPHERS:
            raise Exception("Cypher not supported ({}). Supported cyphers: {}".format(self.hash_function,
                                                                                      SUPPORTED_CIPHERS))

    def encrypt(self, tx_id, debug, logging):
        # Transaction to be encrypted
        # FIXME: The blob data should contain more things that just the transaction. Leaving like this for now.
        tx = unhexlify(self.data)

        # FIXME: tx_id should not be necessary (can be derived from tx SegWit-like). Passing it for now
        # Extend the key using HKDF
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

        if debug:
            logging.info("[Client] creating new blob")
            logging.info("[Client] master key: {}".format(hexlify(master_key).decode()))
            logging.info("[Client] sk: {}".format(hexlify(sk).decode()))
            logging.info("[Client] nonce: {}".format(hexlify(nonce).decode()))
            logging.info("[Client] encrypted_blob: {}".format(encrypted_blob))

        return encrypted_blob
