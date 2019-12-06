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
