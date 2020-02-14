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

# FIXME: Common has not log file, so it needs to log in the same log as the caller. This is a temporary fix.
logger = None


class Cryptographer:
    """
    The :class:`Cryptographer` is the class in charge of all the cryptography in the tower.
    """

    @staticmethod
    def check_data_key_format(data, secret):
        """
        Checks that the data and secret that will be used to by ``encrypt`` / ``decrypt`` are properly
        formatted.

        Args:
              data(:mod:`str`): the data to be encrypted.
              secret(:mod:`str`): the secret used to derive the encryption key.

        Returns:
              :obj:`bool`: Whether or not the ``key`` and ``data`` are properly formatted.

        Raises:
              ValueError: if either the ``key`` or ``data`` is not properly formatted.
        """

        if len(data) % 2:
            error = "Incorrect (Odd-length) value"
            raise ValueError(error)

        if not check_sha256_hex_format(secret):
            error = "Secret must be a 32-byte hex value (64 hex chars)"
            raise ValueError(error)

        return True

    @staticmethod
    def encrypt(blob, secret, rtype="str"):
        """
        Encrypts a given :mod:`Blob <common.cli.blob.Blob>` data using ``CHACHA20POLY1305``.

        ``SHA256(secret)`` is used as ``key``, and ``0 (12-byte)`` as ``iv``.

        Args:
              blob (:mod:`Blob <common.cli.blob.Blob>`): a ``Blob`` object containing a raw penalty transaction.
              secret (:mod:`str`): a value to used to derive the encryption key. Should be the dispute txid.
              rtype(:mod:`str`): the return type for the encrypted value. Can be either ``'str'`` or ``'bytes'``.

        Returns:
              :obj:`str` or :obj:`bytes`: The encrypted data in ``str`` or ``bytes``, depending on ``rtype``.

        Raises:
            ValueError: if ``rtype`` is not ``'str'`` or ``'bytes'``
        """

        if rtype not in ["str", "bytes"]:
            raise ValueError("Wrong return type. Return type must be 'str' or 'bytes'")

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

        if rtype == "str":
            encrypted_blob = hexlify(encrypted_blob).decode("utf8")

        return encrypted_blob

    @staticmethod
    # ToDo: #20-test-tx-decrypting-edge-cases
    def decrypt(encrypted_blob, secret, rtype="str"):
        """
        Decrypts a given :mod:`EncryptedBlob <common.encrypted_blob.EncryptedBlob>` using ``CHACHA20POLY1305``.

        ``SHA256(secret)`` is used as ``key``, and ``0 (12-byte)`` as ``iv``.

        Args:
              encrypted_blob(:mod:`EncryptedBlob <comnmon.encrypted_blob.EncryptedBlob>`): an ``EncryptedBlob`` potentially
                containing a penalty transaction.
              secret (:mod:`str`): a value to used to derive the decryption key. Should be the dispute txid.
              rtype(:mod:`str`): the return type for the decrypted value. Can be either ``'str'`` or ``'bytes'``.

        Returns:
              :obj:`str` or :obj:`bytes`: The decrypted data in ``str`` or ``bytes``, depending on ``rtype``.

        Raises:
            ValueError: if ``rtype`` is not ``'str'`` or ``'bytes'``
        """

        if rtype not in ["str", "bytes"]:
            raise ValueError("Wrong return type. Return type must be 'str' or 'bytes'")

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

            # Change the blob encoding to hex depending on the rtype (default)
            if rtype == "str":
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
            logger.error("Key file not found. Please check your settings")
            return None

        except IOError as e:
            logger.error("I/O error({}): {}".format(e.errno, e.strerror))
            return None

    @staticmethod
    def load_public_key_der(pk_der):
        """
        Creates an :mod:`EllipticCurvePublicKey` object from a given ``DER`` encoded public key.

        Args:
             pk_der(:mod:`str`): a public key encoded in ``DER`` format.

        Returns:
             :mod:`EllipticCurvePublicKey`: An ``EllipticCurvePublicKey`` object.

        Raises:
            UnsupportedAlgorithm: if the key algorithm is not supported.
            ValueError: if the provided ``pk_der`` data cannot be deserialized (wrong size or format).
            TypeError: if the provided ``pk_der`` data is not a string.
        """

        try:
            pk = load_der_public_key(pk_der, backend=default_backend())
            return pk

        except UnsupportedAlgorithm:
            logger.error("Could not deserialize the public key (unsupported algorithm)")

        except ValueError:
            logger.error("The provided data cannot be deserialized (wrong size or format)")

        except TypeError:
            logger.error("The provided data cannot be deserialized (wrong type)")

        return None

    @staticmethod
    def load_private_key_der(sk_der):
        """
        Creates an :mod:`EllipticCurvePrivateKey` object from a given ``DER`` encoded private key.

        Args:
             sk_der(:mod:`str`): a private key encoded in ``DER`` format.

        Returns:
             :mod:`EllipticCurvePrivateKey`: An ``EllipticCurvePrivateKey`` object.

        Raises:
            UnsupportedAlgorithm: if the key algorithm is not supported.
            ValueError: if the provided ``pk_der`` data cannot be deserialized (wrong size or format).
            TypeError: if the provided ``pk_der`` data is not a string.
        """
        try:
            sk = load_der_private_key(sk_der, None, backend=default_backend())
            return sk

        except UnsupportedAlgorithm:
            logger.error("Could not deserialize the private key (unsupported algorithm)")

        except ValueError:
            logger.error("The provided data cannot be deserialized (wrong size or format)")

        except TypeError:
            logger.error("The provided data cannot be deserialized (wrong type)")

        return None

    @staticmethod
    def sign(data, sk, rtype="str"):
        """
        Signs a given data using a given secret key using ECDSA.

        Args:
            data(:mod:`bytes`): the data to be signed.
            sk(:mod:`EllipticCurvePrivateKey`): the ECDSA secret key used to signed the data.
            rtype: the return type for the encrypted value. Can be either ``'str'`` or ``'bytes'``.

        Returns:
           :obj:`str` or :obj:`bytes`: The data signature in ``str`` or ``bytes``, depending on ``rtype``.

        Raises:
            ValueError: if ``rtype`` is not ``'str'`` or ``'bytes'``
        """

        if rtype not in ["str", "bytes"]:
            raise ValueError("Wrong return type. Return type must be 'str' or 'bytes'")

        if not isinstance(sk, ec.EllipticCurvePrivateKey):
            logger.error("The value passed as sk is not a private key (EllipticCurvePrivateKey)")
            return None

        else:
            signature = sk.sign(data, ec.ECDSA(hashes.SHA256()))

            if rtype == "str":
                signature = hexlify(signature).decode("utf-8")

            return signature

    @staticmethod
    def verify(message, signature, pk):
        """
        Verifies if a signature is valid for a given public key and message.

        Args:
            message(:mod:`bytes`): the message that is supposed have been signed.
            signature(:mod:`str`): the potential signature of the message.
            pk(:mod:`EllipticCurvePublicKey`): the public key that is used to try to verify the signature.

        Returns:
            :mod:`bool`: Whether or not the provided signature is valid for the given message and public key.
            Returns ``False`` is the ``key`` is not in the right format or if either the ``message`` or ``pk`` cannot
            be decoded.
        """

        if not isinstance(pk, ec.EllipticCurvePublicKey):
            logger.error("The value passed as pk is not a public key (EllipticCurvePublicKey)")
            return False

        if isinstance(signature, str):
            signature = unhexlify(signature)

        try:
            pk.verify(signature, message, ec.ECDSA(hashes.SHA256()))

            return True

        except InvalidSignature:
            return False
