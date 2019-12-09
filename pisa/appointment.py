import json

from pisa.encrypted_blob import EncryptedBlob


class Appointment:
    """
    The Appointment class contains the information regarding an appointment between a client and the Watchtower.

    Args:
        locator (str): A 16-byte hex-encoded value used by the tower to detect channel breaches. It serves as a trigger
        for the tower to decrypt and broadcast the penalty transaction.
        start_time (int): The block height at which the tower is hired to start watching for breaches.
        end_time (int): The block height at which the tower will stop watching for breaches.
        dispute_delta (int): The `to_self_delay` encoded in the CSV of the HTLC that this appointment is covering.
        encrypted_blob (EncryptedBlob): An `EncryptedBlob` object containing an encrypted penalty transaction. The tower
        will decrypt it and broadcast the penalty transaction upon seeing a breach on the blockchain.
    """

    # DISCUSS: 35-appointment-checks
    def __init__(self, locator, start_time, end_time, dispute_delta, encrypted_blob):
        self.locator = locator
        self.start_time = start_time  # ToDo: #4-standardize-appointment-fields
        self.end_time = end_time  # ToDo: #4-standardize-appointment-fields
        self.dispute_delta = dispute_delta
        self.encrypted_blob = EncryptedBlob(encrypted_blob)

    @classmethod
    def from_dict(cls, appointment_data):
        """
        Builds an appointment from a dictionary.

        This method is useful to load data from a database.

        Args:
            appointment_data (dict): a dictionary containing the following keys:
                `{locator, start_time, end_time, dispute_delta, encrypted_blob}`

        Returns:
            Appointment: An appointment initialized using the provided data.

        Raises:
            ValueError: If one of the mandatory keys is missing in `appointment_data`.
        """

        locator = appointment_data.get("locator")
        start_time = appointment_data.get("start_time")  # ToDo: #4-standardize-appointment-fields
        end_time = appointment_data.get("end_time")  # ToDo: #4-standardize-appointment-fields
        dispute_delta = appointment_data.get("dispute_delta")
        encrypted_blob_data = appointment_data.get("encrypted_blob")

        if any(v is None for v in [locator, start_time, end_time, dispute_delta, encrypted_blob_data]):
            raise ValueError("Wrong appointment data, some fields are missing")

        else:
            appointment = cls(locator, start_time, end_time, dispute_delta, encrypted_blob_data)

        return appointment

    def to_dict(self):
        """
        Exports an `Appointment` as a dictionary.

        Returns:
            appointment (dict): A dictionary containing the `Appointment` attributes.

        """

        # ToDO: #3-improve-appointment-structure
        appointment = {
            "locator": self.locator,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "dispute_delta": self.dispute_delta,
            "encrypted_blob": self.encrypted_blob.data,
        }

        return appointment

    def to_json(self, triggered=False):
        """
        Exports an `Appointment` as a deterministic json encoded string.

        This method ensures that multiple invocations with the same data yield the same value. This is the format used
        to store appointments in the database.

        Args:
            triggered (bool): Whether the dispute has been triggered or not. When an appointment passes from the
            `Watcher` to the `Responder` it is not deleted straightaway. Instead, the appointment is stored in the DB
            flagged as triggered. This aims to ease handling block reorgs in the future.

        Returns:
            appointment (str): A json-encoded str representing the appointment.
        """

        appointment = self.to_dict()

        appointment["triggered"] = triggered

        return json.dumps(appointment, sort_keys=True, separators=(",", ":"))
