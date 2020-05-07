import pyzbase32
from hashlib import sha256, new
from binascii import unhexlify, hexlify
from coincurve.utils import int_to_bytes
from coincurve import PrivateKey, PublicKey
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from common.tools import is_256b_hex_str
from common.exceptions import InvalidKey, InvalidParameter, SignatureError, EncryptionError

LN_MESSAGE_PREFIX = b"Lightning Signed Message:"


def sha256d(message):
    """
    Computes the double sha256 of a given message.

    Args:
        message(:obj:`bytes`): the message to be used as input to the hash function.

    Returns:
        :obj:`bytes`: the sha256d of the given message.
    """

    return sha256(sha256(message).digest()).digest()


def hash_160(message):
    """ Calculates the RIPEMD-160 hash of a given message.

    Args:
        message (:obj:`str`) the message to be hashed.

    Returns:
        :obj:`str`: the ripemd160 hash of the given message.
    """

    # Calculate the RIPEMD-160 hash of the given data.
    md = new("ripemd160")
    md.update(unhexlify(message))
    h160 = md.hexdigest()

    return h160


# NOTCOVERED
def sigrec_encode(rsig_rid):
    """
    Encodes a pk-recoverable signature to be used in LN. ``rsig_rid`` can be obtained trough
    ``PrivateKey.sign_recoverable``. The required format has the recovery id as the last byte, and for signing LN
    messages we need it as the first. From: https://twitter.com/rusty_twit/status/1182102005914800128

    Args:
        rsig_rid(:obj:`bytes`): the signature to be encoded.

    Returns:
        :obj:`bytes`: the encoded signature.
    """

    rsig, rid = rsig_rid[:64], rsig_rid[64]
    sigrec = int_to_bytes(rid + 31) + rsig

    return sigrec


# NOTCOVERED
def sigrec_decode(sigrec):
    """
    Decodes a pk-recoverable signature in the format used by LN to be input to ``PublicKey.from_signature_and_message``.

    Args:
        sigrec(:obj:`bytes`): the signature to be decoded.

    Returns:
        :obj:`bytes`: the decoded signature.

    Raises:
        :obj:`ValueError`: if the SigRec is not properly encoded (first byte is not 31 + recovery id)
    """

    int_rid, rsig = sigrec[0] - 31, sigrec[1:]
    if int_rid < 0:
        raise ValueError("Wrong SigRec")
    else:
        rid = int_to_bytes(int_rid)

    return rsig + rid


class Cryptographer:
    """
    The :class:`Cryptographer` is in charge of all the cryptography in the tower.
    """

    @staticmethod
    def check_data_key_format(data, secret):
        """
        Checks that the data and secret that will be used to by ``encrypt`` / ``decrypt`` are properly formatted.

        Args:
              data(:obj:`str`): the data to be encrypted.
              secret(:obj:`str`): the secret used to derive the encryption key.

        Raises:
              :obj:`InvalidParameter`: if either the ``key`` and/or ``data`` are not properly formatted.
        """

        if len(data) % 2:
            raise InvalidParameter("Incorrect (Odd-length) data", data=data)

        if not is_256b_hex_str(secret):
            raise InvalidParameter("Secret must be a 32-byte hex value (64 hex chars)", secret=secret)

    @staticmethod
    def encrypt(message, secret):
        """
        Encrypts a given message data using ``CHACHA20POLY1305``.

        ``SHA256(secret)`` is used as ``key``, and ``0 (12-byte)`` as ``iv``.

        Args:
              message (:obj:`str`): a message to be encrypted. Should be the hex-encoded commitment_tx.
              secret (:obj:`str`): a value to used to derive the encryption key. Should be the dispute txid.

        Returns:
              :obj:`str`: The encrypted data (hex-encoded).

        Raises:
              :obj:`InvalidParameter`: if either the ``key`` and/or ``data`` are not properly formatted.
        """

        Cryptographer.check_data_key_format(message, secret)

        # sk is the H(txid) (32-byte) and nonce is set to 0 (12-byte)
        sk = sha256(unhexlify(secret)).digest()
        nonce = bytearray(12)

        # Encrypt the data
        cipher = ChaCha20Poly1305(sk)
        encrypted_blob = cipher.encrypt(nonce=nonce, data=unhexlify(message), associated_data=None)
        encrypted_blob = hexlify(encrypted_blob).decode("utf8")

        return encrypted_blob

    @staticmethod
    # ToDo: #20-test-tx-decrypting-edge-cases
    def decrypt(encrypted_blob, secret):
        """
        Decrypts a given encrypted_blob using ``CHACHA20POLY1305``.

        ``SHA256(secret)`` is used as ``key``, and ``0 (12-byte)`` as ``iv``.

        Args:
            encrypted_blob(:obj:`str`): an encrypted blob of data potentially containing a penalty transaction.
            secret (:obj:`str`): a value used to derive the decryption key. Should be the dispute txid.

        Returns:
              :obj:`str`: The decrypted data (hex-encoded).

        Raises:
              :obj:`InvalidParameter`: if either the ``key`` and/or ``data`` are not properly formatted.
              :obj:`EncryptionError`: if the data cannot be decrypted with the given key.
        """

        Cryptographer.check_data_key_format(encrypted_blob, secret)

        # sk is the H(txid) (32-byte) and nonce is set to 0 (12-byte)
        sk = sha256(unhexlify(secret)).digest()
        nonce = bytearray(12)

        # Decrypt
        cipher = ChaCha20Poly1305(sk)
        data = unhexlify(encrypted_blob)

        try:
            blob = cipher.decrypt(nonce=nonce, data=data, associated_data=None)
            blob = hexlify(blob).decode("utf8")

        except InvalidTag:
            raise EncryptionError("Cannot decrypt blob with the provided key", blob=encrypted_blob, key=secret)

        return blob

    @staticmethod
    def load_key_file(file_path):
        """
        Loads a key from a key file.

        Args:
            file_path (:obj:`str`): the path to the key file to be loaded.

        Returns:
            :obj:`bytes`: the key file data if the file can be found and read.

        Raises:
             :obj:`InvalidParameter`: if the file_path has wrong format or cannot be found.
             :obj:`InvalidKey`: if the key cannot be loaded from the file. It covers temporary I/O errors.
        """

        if not isinstance(file_path, str):
            raise InvalidParameter("Key file path was expected, {} received".format(type(file_path)))

        try:
            with open(file_path, "rb") as key_file:
                key = key_file.read()
            return key

        except FileNotFoundError:
            raise InvalidParameter("Key file not found at {}. Please check your settings".format(file_path))

        except IOError as e:
            raise InvalidKey("Key file cannot be loaded", exception=e)

    @staticmethod
    def load_private_key_der(sk_der):
        """
        Creates a :obj:`PrivateKey` from a given ``DER`` encoded private key.

        Args:
             sk_der(:obj:`str`): a private key encoded in ``DER`` format.

        Returns:
             :obj:`PrivateKey`: A ``PrivateKey`` object if the private key can be loaded.

        Raises:
            :obj:`InvalidKey`: if a ``PrivateKey`` cannot be loaded from the given data.
        """

        try:
            sk = PrivateKey.from_der(sk_der)
            return sk

        except ValueError:
            raise InvalidKey("The provided key data cannot be deserialized (wrong size or format)")

        except TypeError:
            raise InvalidKey("The provided key data cannot be deserialized (wrong type)")

    @staticmethod
    def sign(message, sk):
        """
        Signs a given message with a given secret key using ECDSA over secp256k1.

        Args:
            message(:obj:`bytes`): the data to be signed.
            sk(:obj:`PrivateKey`): the ECDSA secret key to be used to sign the data.

        Returns:
           :obj:`str`: The zbase32 signature of the given message is it can be signed.

        Raises:
             :obj:`InvalidParameter`: if the message and/or secret key have a wrong value.
             :obj:`SignatureError`: if there is an error during the signing process.
        """

        if not isinstance(message, bytes):
            raise InvalidParameter("Wrong value passed as message. Received {}, expected (bytes)".format(type(message)))

        if not isinstance(sk, PrivateKey):
            raise InvalidParameter("Wrong value passed as sk. Received {}, expected (PrivateKey)".format(type(message)))

        try:
            rsig_rid = sk.sign_recoverable(LN_MESSAGE_PREFIX + message, hasher=sha256d)
            sigrec = sigrec_encode(rsig_rid)
            zb32_sig = pyzbase32.encode_bytes(sigrec).decode()

        except ValueError as e:
            raise SignatureError("Couldn't sign the message. " + str(e))

        return zb32_sig

    @staticmethod
    def recover_pk(message, zb32_sig):
        """
        Recovers an ECDSA public key from a given message and zbase32 signature.

        Args:
            message(:obj:`bytes`): original message from where the signature was generated.
            zb32_sig(:obj:`str`): the zbase32 signature of the message.

        Returns:
           :obj:`PublicKey`: The public key if it can be recovered.

        Raises:
             :obj:`InvalidParameter`: if the message and/or signature have a wrong value.
             :obj:`SignatureError`: if a public key cannot be recovered from the given signature.
        """

        if not isinstance(message, bytes):
            raise InvalidParameter("Wrong value passed as message. Received {}, expected (bytes)".format(type(message)))

        if not isinstance(zb32_sig, str):
            raise InvalidParameter(
                "Wrong value passed as zbase32_sig. Received {}, expected (str)".format(type(zb32_sig))
            )

        sigrec = pyzbase32.decode_bytes(zb32_sig)

        try:
            rsig_recid = sigrec_decode(sigrec)
            pk = PublicKey.from_signature_and_message(rsig_recid, LN_MESSAGE_PREFIX + message, hasher=sha256d)
            return pk

        except ValueError as e:
            # Several errors fit here: Signature length != 65, wrong recover id and failed to parse signature.
            # All of them return raise ValueError.
            raise SignatureError("Cannot recover a public key from the given signature. " + str(e))

        except Exception as e:
            if "failed to recover ECDSA public key" in str(e):
                raise SignatureError("Cannot recover a public key from the given signature")
            else:
                raise SignatureError("Unknown exception. " + str(e))

    @staticmethod
    def get_compressed_pk(pk):
        """
        Computes a compressed, hex-encoded, public key given a ``PublicKey``.

        Args:
            pk(:obj:`PublicKey`): a given public key.

        Returns:
            :obj:`str`: A compressed, hex-encoded, public key (33-byte long) if it can be compressed.

        Raises:
             :obj:`InvalidParameter`: if the value passed as public key is not a PublicKey object.
             :obj:`InvalidKey`: if the public key has not been properly created.
        """

        if not isinstance(pk, PublicKey):
            raise InvalidParameter("Wrong value passed as pk. Received {}, expected (PublicKey)".format(type(pk)))

        try:
            compressed_pk = pk.format(compressed=True)
            return hexlify(compressed_pk).decode("utf-8")

        except TypeError as e:
            raise InvalidKey("PublicKey has invalid initializer", error=str(e))
