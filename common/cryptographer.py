import pyzbase32
from hashlib import sha256, new
from binascii import unhexlify, hexlify
from coincurve.utils import int_to_bytes
from coincurve import PrivateKey, PublicKey
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from common.tools import is_256b_hex_str

LN_MESSAGE_PREFIX = b"Lightning Signed Message:"


def sha256d(message):
    """
    Computes the double sha256 of a given by message.

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


# FIXME: Common has not log file, so it needs to log in the same log as the caller. This is a temporary fix.
logger = None


class Cryptographer:
    """
    The :class:`Cryptographer` is in charge of all the cryptography in the tower.
    """

    @staticmethod
    def check_data_key_format(data, secret):
        """
        Checks that the data and secret that will be used to by ``encrypt`` / ``decrypt`` are properly
        formatted.

        Args:
              data(:obj:`str`): the data to be encrypted.
              secret(:obj:`str`): the secret used to derive the encryption key.

        Returns:
              :obj:`bool`: Whether or not the ``key`` and ``data`` are properly formatted.

        Raises:
              :obj:`ValueError`: if either the ``key`` or ``data`` is not properly formatted.
        """

        if len(data) % 2:
            error = "Incorrect (Odd-length) value"
            raise ValueError(error)

        if not is_256b_hex_str(secret):
            error = "Secret must be a 32-byte hex value (64 hex chars)"
            raise ValueError(error)

        return True

    @staticmethod
    def encrypt(blob, secret):
        """
        Encrypts a given :obj:`Blob <common.cli.blob.Blob>` data using ``CHACHA20POLY1305``.

        ``SHA256(secret)`` is used as ``key``, and ``0 (12-byte)`` as ``iv``.

        Args:
              blob (:obj:`Blob <common.cli.blob.Blob>`): a ``Blob`` object containing a raw penalty transaction.
              secret (:obj:`str`): a value to used to derive the encryption key. Should be the dispute txid.

        Returns:
              :obj:`str`: The encrypted data (hex encoded).

        Raises:
              :obj:`ValueError`: if either the ``secret`` or ``blob`` is not properly formatted.
        """

        Cryptographer.check_data_key_format(blob.data, secret)

        # Transaction to be encrypted
        # FIXME: The blob data should contain more things that just the transaction. Leaving like this for now.
        tx = unhexlify(blob.data)

        # sk is the H(txid) (32-byte) and nonce is set to 0 (12-byte)
        sk = sha256(unhexlify(secret)).digest()
        nonce = bytearray(12)

        logger.debug("Encrypting blob", sk=hexlify(sk).decode(), nonce=hexlify(nonce).decode(), blob=blob.data)

        # Encrypt the data
        cipher = ChaCha20Poly1305(sk)
        encrypted_blob = cipher.encrypt(nonce=nonce, data=tx, associated_data=None)
        encrypted_blob = hexlify(encrypted_blob).decode("utf8")

        return encrypted_blob

    @staticmethod
    # ToDo: #20-test-tx-decrypting-edge-cases
    def decrypt(encrypted_blob, secret):
        """
        Decrypts a given :obj:`EncryptedBlob <common.encrypted_blob.EncryptedBlob>` using ``CHACHA20POLY1305``.

        ``SHA256(secret)`` is used as ``key``, and ``0 (12-byte)`` as ``iv``.

        Args:
            encrypted_blob(:obj:`EncryptedBlob <common.encrypted_blob.EncryptedBlob>`): an ``EncryptedBlob``
                potentially containing a penalty transaction.
            secret (:obj:`str`): a value to used to derive the decryption key. Should be the dispute txid.

        Returns:
              :obj:`str`: The decrypted data (hex encoded).

        Raises:
              :obj:`ValueError`: if either the ``secret`` or ``encrypted_blob`` is not properly formatted.
        """

        Cryptographer.check_data_key_format(encrypted_blob.data, secret)

        # sk is the H(txid) (32-byte) and nonce is set to 0 (12-byte)
        sk = sha256(unhexlify(secret)).digest()
        nonce = bytearray(12)

        logger.info(
            "Decrypting blob",
            sk=hexlify(sk).decode(),
            nonce=hexlify(nonce).decode(),
            encrypted_blob=encrypted_blob.data,
        )

        # Decrypt
        cipher = ChaCha20Poly1305(sk)
        data = unhexlify(encrypted_blob.data)

        try:
            blob = cipher.decrypt(nonce=nonce, data=data, associated_data=None)
            blob = hexlify(blob).decode("utf8")

        except InvalidTag:
            blob = None
            logger.error("Can't decrypt blob with the provided key")

        return blob

    @staticmethod
    def load_key_file(file_path):
        """
        Loads a key from a key file.

        Args:
            file_path (:obj:`str`): the path to the key file to be loaded.

        Returns:
            :obj:`bytes` or :obj:`None`: the key file data if the file can be found and read. ``None`` otherwise.
        """

        if not isinstance(file_path, str):
            logger.error("Key file path was expected, {} received".format(type(file_path)))
            return None

        try:
            with open(file_path, "rb") as key_file:
                key = key_file.read()
            return key

        except FileNotFoundError:
            logger.error("Key file not found at {}. Please check your settings".format(file_path))
            return None

        except IOError as e:
            logger.error("I/O error({}): {}".format(e.errno, e.strerror))
            return None

    @staticmethod
    def load_private_key_der(sk_der):
        """
        Creates a :obj:`PrivateKey` from a given ``DER`` encoded private key.

        Args:
             sk_der(:obj:`str`): a private key encoded in ``DER`` format.

        Returns:
             :obj:`PrivateKey` or :obj:`None`: A ``PrivateKey`` object. if the private key can be loaded. `None`
             otherwise.
        """
        try:
            sk = PrivateKey.from_der(sk_der)
            return sk

        except ValueError:
            logger.error("The provided data cannot be deserialized (wrong size or format)")

        except TypeError:
            logger.error("The provided data cannot be deserialized (wrong type)")

        return None

    @staticmethod
    def sign(message, sk):
        """
        Signs a given data using a given secret key using ECDSA over secp256k1.

        Args:
            message(:obj:`bytes`): the data to be signed.
            sk(:obj:`PrivateKey`): the ECDSA secret key used to signed the data.

        Returns:
           :obj:`str` or :obj:`None`: The zbase32 signature of the given message is it can be signed. `None` otherwise.
        """

        if not isinstance(message, bytes):
            logger.error("The message must be bytes. {} received".format(type(message)))
            return None

        if not isinstance(sk, PrivateKey):
            logger.error("The value passed as sk is not a private key (PrivateKey)")
            return None

        try:
            rsig_rid = sk.sign_recoverable(LN_MESSAGE_PREFIX + message, hasher=sha256d)
            sigrec = sigrec_encode(rsig_rid)
            zb32_sig = pyzbase32.encode_bytes(sigrec).decode()

        except ValueError:
            logger.error("Couldn't sign the message")
            return None

        return zb32_sig

    @staticmethod
    def recover_pk(message, zb32_sig):
        """
        Recovers an ECDSA public key from a given message and zbase32 signature.

        Args:
            message(:obj:`bytes`): original message from where the signature was generated.
            zb32_sig(:obj:`str`): the zbase32 signature of the message.

        Returns:
           :obj:`PublicKey` or :obj:`None`: The recovered public key if it can be recovered. `None` otherwise.
        """

        if not isinstance(message, bytes):
            logger.error("The message must be bytes. {} received".format(type(message)))
            return None

        if not isinstance(zb32_sig, str):
            logger.error("The zbase32_sig must be str. {} received".format(type(zb32_sig)))
            return None

        sigrec = pyzbase32.decode_bytes(zb32_sig)

        try:
            rsig_recid = sigrec_decode(sigrec)
            pk = PublicKey.from_signature_and_message(rsig_recid, LN_MESSAGE_PREFIX + message, hasher=sha256d)
            return pk

        except ValueError as e:
            # Several errors fit here: Signature length != 65, wrong recover id and failed to parse signature.
            # All of them return raise ValueError.
            logger.error(str(e))
            return None

        except Exception as e:
            if "failed to recover ECDSA public key" in str(e):
                logger.error("Cannot recover public key from signature")
            else:
                logger.error("Unknown exception", error=str(e))

            return None

    @staticmethod
    def verify_rpk(pk, rpk):
        """
        Verifies that that a recovered public key matches a given one.

        Args:
            pk(:obj:`PublicKey`): a given public key (provided by the user).
            rpk(:obj:`PublicKey`): a public key recovered via ``recover_pk``.

        Returns:
            :obj:`bool`: True if the public keys match, False otherwise.
        """

        return pk.point() == rpk.point()

    @staticmethod
    def get_compressed_pk(pk):
        """
        Computes a compressed, hex-encoded, public key given a ``PublicKey``.

        Args:
            pk(:obj:`PublicKey`): a given public key.

        Returns:
            :obj:`str` or :obj:`None`: A compressed, hex-encoded, public key (33-byte long) if it can be compressed.
            `None` oterwise.
        """

        if not isinstance(pk, PublicKey):
            logger.error("The received data is not a PublicKey object")
            return None

        try:
            compressed_pk = pk.format(compressed=True)
            return hexlify(compressed_pk).decode("utf-8")

        except TypeError as e:
            logger.error("PublicKey has invalid initializer", error=str(e))
            return None
