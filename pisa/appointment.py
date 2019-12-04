import json

from pisa.encrypted_blob import EncryptedBlob


# Basic appointment structure
class Appointment:
    # DISCUSS: 35-appointment-checks
    def __init__(self, locator, start_time, end_time, dispute_delta, encrypted_blob, triggered=False):
        self.locator = locator
        self.start_time = start_time  # ToDo: #4-standardize-appointment-fields
        self.end_time = end_time  # ToDo: #4-standardize-appointment-fields
        self.dispute_delta = dispute_delta
        self.encrypted_blob = EncryptedBlob(encrypted_blob)
        self.triggered = triggered

    @classmethod
    def from_dict(cls, appointment_data):
        locator = appointment_data.get("locator")
        start_time = appointment_data.get("start_time")  # ToDo: #4-standardize-appointment-fields
        end_time = appointment_data.get("end_time")  # ToDo: #4-standardize-appointment-fields
        dispute_delta = appointment_data.get("dispute_delta")
        encrypted_blob_data = appointment_data.get("encrypted_blob")

        triggered = True if appointment_data.get("triggered") is True else False

        if any(v is None for v in [locator, start_time, end_time, dispute_delta, encrypted_blob_data, triggered]):
            raise ValueError("Wrong appointment data, some fields are missing")

        else:
            appointment = cls(locator, start_time, end_time, dispute_delta, encrypted_blob_data, triggered)

        return appointment

    def to_dict(self):
        # ToDO: #3-improve-appointment-structure
        appointment = {
            "locator": self.locator,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "dispute_delta": self.dispute_delta,
            "encrypted_blob": self.encrypted_blob.data,
            "triggered": self.triggered,
        }

        return appointment

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def serialize(self):
        data = self.to_dict()
        data.pop("triggered")
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
