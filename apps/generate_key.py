import ecdsa
import os.path
from sys import exit

# Simple tool to generate an ECDSA private key using the secp256k1 curve and save it to signing_key.pem

FILE_NAME = 'signing_key.pem'

if __name__ == '__main__':
    if os.path.exists(FILE_NAME):
        print("A key with name \"{}\" already exists. Aborting.".format(FILE_NAME))
        exit(1)

    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
    open(FILE_NAME, 'wb').write(sk.to_pem())
    print("Saved key \"{}\".".format(FILE_NAME))
