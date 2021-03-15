import datetime
import os.path
import pyzbase32
from pathlib import Path
from hashlib import sha256, new
from coincurve.utils import int_to_bytes
from coincurve import PrivateKey, PublicKey
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography import x509
from cryptography.x509.oid import NameOID

from common.tools import is_256b_hex_str
from common.exceptions import InvalidKey, InvalidParameter, SignatureError, EncryptionError

LN_MESSAGE_PREFIX = b"Lightning Signed Message:"


def sha256d(message):
    """
    Computes the double sha256 of a given message.

    Args:
        message(:obj:`bytes`): the message to be used as input to the hash function.

    Returns:
        :obj:`bytes`: The sha256d of the given message.
    """

    return sha256(sha256(message).digest()).digest()


def hash_160(message):
    """ Calculates the RIPEMD-160 hash of a given message.

    Args:
        message (:obj:`str`): the message to be hashed.

    Returns:
        :obj:`str`: The ripemd160 hash of the given message.
    """

    # Calculate the RIPEMD-160 hash of the given data.
    md = new("ripemd160")
    md.update(bytes.fromhex(message))
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
        :obj:`bytes`: The encoded signature.
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
        :obj:`bytes`: The decoded signature.

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
        sk = sha256(bytes.fromhex(secret)).digest()
        nonce = bytearray(12)

        # Encrypt the data
        cipher = ChaCha20Poly1305(sk)
        encrypted_blob = cipher.encrypt(nonce=nonce, data=bytes.fromhex(message), associated_data=None).hex()

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
        sk = sha256(bytes.fromhex(secret)).digest()
        nonce = bytearray(12)

        # Decrypt
        cipher = ChaCha20Poly1305(sk)
        data = bytes.fromhex(encrypted_blob)

        try:
            blob = cipher.decrypt(nonce=nonce, data=data, associated_data=None).hex()

        except InvalidTag:
            raise EncryptionError("Cannot decrypt blob with the provided key", blob=encrypted_blob, key=secret)

        return blob

    @staticmethod
    def generate_key():
        """
        Generates an ECDSA private key (over secp256k1).

        Returns:
            :obj:`PrivateKey`: A private key.
        """
        return PrivateKey()

    @staticmethod
    def save_crypto_file(crypto_data, name, data_dir):
        """
        Saves cryptographic data, like a key or certificate, to disk in format.

        Args:
            crypto_data (:obj:`bytes`): the key to be saved to disk.
            name (:obj:`str`): the name of the key file to be generated.
            data_dir (:obj:`str`): the data directory where the file will be saved.

        Raises:
            :obj:`InvalidParameter`: If the given crypto data is not bytes or the name or data_dir are not strings.
        """

        if not isinstance(crypto_data, bytes):
            raise InvalidParameter("Crypto data must be bytes, {} received".format(type(crypto_data)))

        if not isinstance(name, str):
            raise InvalidParameter("Crypto data name must be str, {} received".format(type(name)))

        if not isinstance(data_dir, str):
            raise InvalidParameter("Data dir must be str, {} received".format(type(data_dir)))

        # Create the output folder it it does not exist (and all the parents if they don't either)
        Path(data_dir).mkdir(parents=True, exist_ok=True)

        with open(os.path.join(data_dir, "{}".format(name)), "wb") as crypto_out:
            crypto_out.write(crypto_data)

    @staticmethod
    def load_key_file(file_path):
        """
        Loads a key or certificate from a disk file.

        Args:
            file_path (:obj:`str`): the path to the key or certificate file to be loaded.

        Returns:
            :obj:`bytes`: The key or certificate file data if the file can be found and read.

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
             :obj:`PrivateKey`: A :obj:`PrivateKey` object if the private key can be loaded.

        Raises:
            :obj:`InvalidKey`: if a :obj:`PrivateKey` cannot be loaded from the given data.
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
        Computes a compressed, hex-encoded, public key given a :obj:`PublicKey` .

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
            return pk.format(compressed=True).hex()

        except TypeError as e:
            raise InvalidKey("PublicKey has invalid initializer", error=str(e))


    @staticmethod
    def generate_cert_key():
        """
        Generates an RSA key with which to self-sign our TSL certificate and converts it to PEM format.
       
        Returns:
            :obj:`bytes`: An RSA key in PEM format.
        """
        sk = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        sk_pem = sk.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        return sk_pem


    @staticmethod
    def generate_self_signed_cert(cert_key_path):
        """
        Generates a self-signed TLS certificate for securing the connection between the CLI and the server.

        Args:
            cert_key_path(:obj:`str`): Path to RSA key.
            
        Returns:
            :obj:`Certificate`: A x509 certificate.

        Raises:
            :obj:`InvalidKey`: if the RSA key file is invalid or could not be found.

        """
        try:
            sk_pem = Cryptographer.load_key_file(cert_key_path)

        except (InvalidParameter, InvalidKey):
            raise InvalidKey("Failed to load RSA key needed for TLS certificate")


        sk = load_pem_private_key(sk_pem, None)

        # get public key from private key
        pk = sk.public_key()

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"Teos watchtower"),
            x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
        ])

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            pk
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(datetime.datetime.utcnow()).not_valid_after(
            # Our certificate will be valid for 365 days
            datetime.datetime.utcnow() + datetime.timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
            critical=False,
        ).sign(sk, hashes.SHA256())

        cert = cert.public_bytes(serialization.Encoding.PEM)

        return cert
