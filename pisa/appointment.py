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

    @classmethod
    def from_dict(cls, appointment_data):
        locator = appointment_data.get("locator")
        start_time = appointment_data.get("start_time")    # ToDo: #4-standardize-appointment-fields
        end_time = appointment_data.get("end_time")    # ToDo: #4-standardize-appointment-fields
        dispute_delta = appointment_data.get("dispute_delta")
        encrypted_blob_data = appointment_data.get("encrypted_blob")
        cipher = appointment_data.get("cipher")
        hash_function = appointment_data.get("hash_function")

        if all([locator, start_time, end_time, dispute_delta, encrypted_blob_data, cipher, hash_function]) is not None:
            appointment = cls(locator, start_time, end_time, dispute_delta, EncryptedBlob(encrypted_blob_data), cipher,
                              hash_function)

        else:
            raise ValueError("Wrong appointment data, some fields are missing")

        return appointment

    def to_dict(self):
        # ToDO: #3-improve-appointment-structure
        appointment = {"locator": self.locator, "start_time": self.start_time, "end_time": self.end_time,
                       "dispute_delta": self.dispute_delta, "encrypted_blob": self.encrypted_blob.data,
                       "cipher": self.cipher, "hash_function": self.hash_function}

        return appointment

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True, separators=(',', ':'))
