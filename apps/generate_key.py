import ecdsa


if __name__ == '__main__':
    sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
    print(sk.to_der())
