import os.path
from getopt import getopt
from sys import argv, exit

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


"""
Simple way too to generate an ECDSA key pair using the secp256k1 curve and store it on disk.

Default output dir = .
Default key naming = teos_sk.der and teos_pk.der

The output dir and naming can be changed using the -n and -d command line options, respectively.

DISCLAIMER: Use this for testing only, using keys generated from this file in production is highly unadvised.
"""


def save_sk(sk, filename):
    der = sk.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    with open(filename, "wb") as der_out:
        der_out.write(der)


def save_pk(pk, filename):
    der = pk.public_bytes(encoding=serialization.Encoding.X962, format=serialization.PublicFormat.CompressedPoint)
    with open(filename, "wb") as der_out:
        der_out.write(der)


if __name__ == "__main__":
    name = "teos"
    output_dir = "."

    opts, _ = getopt(argv[1:], "n:d:", ["name", "dir"])
    for opt, arg in opts:
        if opt in ["-n", "--name"]:
            name = arg

        if opt in ["-d", "--dir"]:
            output_dir = arg

    if output_dir.endswith("/"):
        output_dir = output_dir[:-1]

    SK_FILE_NAME = "{}/{}_sk.der".format(output_dir, name)
    PK_FILE_NAME = "{}/{}_pk.der".format(output_dir, name)

    if os.path.exists(SK_FILE_NAME):
        print('A key with name "{}" already exists. Aborting.'.format(SK_FILE_NAME))
        exit(1)

    sk = ec.generate_private_key(ec.SECP256K1, default_backend())
    pk = sk.public_key()

    save_sk(sk, SK_FILE_NAME)
    save_pk(pk, PK_FILE_NAME)
    print('Saved private key "{}" and public key "{}".'.format(SK_FILE_NAME, PK_FILE_NAME))
