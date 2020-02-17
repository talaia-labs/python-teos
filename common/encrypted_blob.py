class EncryptedBlob:
    def __init__(self, data):
        self.data = data

    def __eq__(self, other):
        return isinstance(other, EncryptedBlob) and self.data == other.data
