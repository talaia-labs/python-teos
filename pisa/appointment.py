import json

from pisa.encrypted_blob import EncryptedBlob


# Basic appointment structure
class Appointment:
    # DISCUSS: 35-appointment-checks
    def __init__(self, locator, start_time, end_time, dispute_delta, encrypted_blob, cipher, hash_function):
        self.locator = locator
        self.start_time = start_time    # ToDo: #4-standardize-appointment-fields
        self.end_time = end_time    # ToDo: #4-standardize-appointment-fields
        self.dispute_delta = dispute_delta
        self.encrypted_blob = EncryptedBlob(encrypted_blob)
        self.cipher = cipher
        self.hash_function = hash_function

    def to_dict(self):
        appointment = {"locator": self.locator, "start_time": self.start_time, "end_time": self.end_time,
                       "dispute_delta": self.dispute_delta, "encrypted_blob": self.encrypted_blob.data,
                       "cipher": self.cipher, "hash_function": self.hash_function}

        return appointment

        # ToDO: #3-improve-appointment-structure

    def to_json(self):
        return json.dumps(self.to_dict())
