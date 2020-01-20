import os.path
from getopt import getopt
from sys import argv, exit

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


# Simple tool to generate an ECDSA private key using the secp256k1 curve and save private and public keys
# as 'pisa_sk.der' 'and pisa_pk.der', respectively.


def save_sk(sk, filename):
    der = sk.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    with open(filename, "wb") as der_out:
        der_out.write(der)


def save_pk(pk, filename):
    der = pk.public_bytes(encoding=serialization.Encoding.DER, format=serialization.PublicFormat.SubjectPublicKeyInfo)
    with open(filename, "wb") as der_out:
        der_out.write(der)


if __name__ == "__main__":
    name = "pisa"

    opts, _ = getopt(argv[1:], "n:", ["name"])
    for opt, arg in opts:
        if opt in ["-n", "--name"]:
            name = arg

    SK_FILE_NAME = "../{}_sk.der".format(name)
    PK_FILE_NAME = "../{}_pk.der".format(name)

    if os.path.exists(SK_FILE_NAME):
        print('A key with name "{}" already exists. Aborting.'.format(SK_FILE_NAME))
        exit(1)

    sk = ec.generate_private_key(ec.SECP256K1, default_backend())
    pk = sk.public_key()

    save_sk(sk, SK_FILE_NAME)
    save_pk(pk, PK_FILE_NAME)
    print('Saved private key "{}" and public key "{}".'.format(SK_FILE_NAME, PK_FILE_NAME))
