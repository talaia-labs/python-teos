import os.path
from pathlib import Path
from binascii import hexlify
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from exceptions import InvalidKey
from common.cryptographer import Cryptographer


def save_key(sk, filename):
    """
    Saves secret key on disk.

    Args:
        sk (:obj:`PrivateKey`): a private key file to be saved on disk.
        filename (:obj:`str`): the name that will be given to the key file.
    """

    der = sk.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    with open(filename, "wb") as der_out:
        der_out.write(der)


def generate_keys(data_dir):
    """
    Generates a key pair for the client.

    Args:
        data_dir (:obj:`str`): path to data directory where the keys will be stored.

    Returns:
        :obj:`tuple`: a tuple containing a ``PrivateKey`` and a ``str`` representing the client sk and compressed
        pk respectively.

    Raises:
        :obj:`FileExistsError`: if the key pair already exists in the given directory.
    """

    # Create the output folder it it does not exist (and all the parents if they don't either)
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    sk_file_name = os.path.join(data_dir, "cli_sk.der")

    if os.path.exists(sk_file_name):
        raise FileExistsError("The client key pair already exists")

    sk = ec.generate_private_key(ec.SECP256K1, default_backend())
    save_key(sk, sk_file_name)

    compressed_pk = sk.public_key().public_bytes(
        encoding=serialization.Encoding.X962, format=serialization.PublicFormat.CompressedPoint
    )

    return sk, hexlify(compressed_pk).decode("utf-8")


def load_keys(data_dir):
    """
    Loads a the client key pair.

    Args:
        data_dir (:obj:`str`): path to data directory where the keys are stored.

    Returns:
        :obj:`tuple`: a tuple containing a ``PrivateKey`` and a ``str`` representing the client sk and compressed
        pk respectively.

    Raises:
        :obj:`InvalidKey <cli.exceptions.InvalidKey>`: if any of the keys is invalid or cannot be loaded.
    """

    if not isinstance(data_dir, str):
        raise ValueError("Invalid data_dir. Please check your settings")

    sk_file_path = os.path.join(data_dir, "cli_sk.der")

    cli_sk_der = Cryptographer.load_key_file(sk_file_path)
    cli_sk = Cryptographer.load_private_key_der(cli_sk_der)

    if cli_sk is None:
        raise InvalidKey("Client private key is invalid or cannot be parsed")

    compressed_cli_pk = Cryptographer.get_compressed_pk(cli_sk.public_key)

    if compressed_cli_pk is None:
        raise InvalidKey("Client public key cannot be loaded")

    return cli_sk, compressed_cli_pk
