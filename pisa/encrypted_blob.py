from pisa.conf import SUPPORTED_CIPHERS, SUPPORTED_HASH_FUNCTIONS


class EncryptedBlob:
    def __init__(self, data, cipher="AES-GCM-128", hash_function="SHA256"):
        if cipher in SUPPORTED_CIPHERS:
            self.cipher = cipher

        else:
            raise ValueError("Cipher not supported")

        if hash_function in SUPPORTED_HASH_FUNCTIONS:
            self.hash_function = hash_function

        else:
            raise ValueError("Hash function not supported")

        self.data = data

    def __eq__(self, other):
        return isinstance(other, EncryptedBlob) and self.data == other.data
