import os.path
from sys import exit

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


# Simple tool to generate an ECDSA private key using the secp256k1 curve and save private and public keys
# as 'pisa_sk.pem' 'and pisa_pk.pem', respectively.

SK_FILE_NAME = "pisa_sk.pem"
PK_FILE_NAME = "pisa_pk.pem"


def save_sk(sk, filename):
    pem = sk.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    with open(filename, "wb") as pem_out:
        pem_out.write(pem)


def save_pk(pk, filename):
    pem = pk.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo)
    with open(filename, "wb") as pem_out:
        pem_out.write(pem)


if __name__ == "__main__":
    if os.path.exists(SK_FILE_NAME):
        print('A key with name "{}" already exists. Aborting.'.format(SK_FILE_NAME))
        exit(1)

    sk = ec.generate_private_key(ec.SECP256K1, default_backend())
    pk = sk.public_key()

    save_sk(sk, SK_FILE_NAME)
    save_pk(pk, PK_FILE_NAME)
    print('Saved private key "{}" and public key "{}".'.format(SK_FILE_NAME, PK_FILE_NAME))
