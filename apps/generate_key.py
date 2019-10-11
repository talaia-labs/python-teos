import ecdsa
import os.path
from sys import exit

# Simple tool to generate an ECDSA private key using the secp256k1 curve and save private and public keys
# as signing_key_priv.pem and signing_key_pub.pem

FILE_NAME_PRIV = 'signing_key_priv.pem'
FILE_NAME_PUB = 'signing_key_pub.pem'

if __name__ == '__main__':
    if os.path.exists(FILE_NAME_PRIV):
        print("A key with name \"{}\" already exists. Aborting.".format(FILE_NAME_PRIV))
        exit(1)

    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
    pk = sk.get_verifying_key()

    open(FILE_NAME_PRIV, 'wb').write(sk.to_pem())
    open(FILE_NAME_PUB, 'wb').write(pk.to_pem())
    print("Saved private key \"{}\" and public key \"{}\".".format(FILE_NAME_PRIV, FILE_NAME_PUB))
