import json
import struct
from binascii import unhexlify

from common.encrypted_blob import EncryptedBlob


class Appointment:
    """
    The :class:`Appointment` contains the information regarding an appointment between a client and the Watchtower.

    Args:
        locator (:mod:`str`): A 16-byte hex-encoded value used by the tower to detect channel breaches. It serves as a trigger
            for the tower to decrypt and broadcast the penalty transaction.
        start_time (:mod:`int`): The block height where the tower is hired to start watching for breaches.
        end_time (:mod:`int`): The block height where the tower will stop watching for breaches.
        to_self_delay (:mod:`int`): The ``to_self_delay`` encoded in the ``csv`` of the ``htlc`` that this appointment is
            covering.
        encrypted_blob (:obj:`EncryptedBlob <common.encrypted_blob.EncryptedBlob>`): An ``EncryptedBlob`` object
            containing an encrypted penalty transaction. The tower will decrypt it and broadcast the penalty transaction
            upon seeing a breach on the blockchain.
    """

    # DISCUSS: 35-appointment-checks
    def __init__(self, locator, start_time, end_time, to_self_delay, encrypted_blob):
        self.locator = locator
        self.start_time = start_time  # ToDo: #4-standardize-appointment-fields
        self.end_time = end_time  # ToDo: #4-standardize-appointment-fields
        self.to_self_delay = to_self_delay
        self.encrypted_blob = EncryptedBlob(encrypted_blob)

    @classmethod
    def from_dict(cls, appointment_data):
        """
        Builds an appointment from a dictionary.

        This method is useful to load data from a database.

        Args:
            appointment_data (:mod:`dict`): a dictionary containing the following keys:
                ``{locator, start_time, end_time, to_self_delay, encrypted_blob}``

        Returns:
            :obj:`Appointment <pisa.appointment.Appointment>`: An appointment initialized using the provided data.

        Raises:
            ValueError: If one of the mandatory keys is missing in ``appointment_data``.
        """

        locator = appointment_data.get("locator")
        start_time = appointment_data.get("start_time")  # ToDo: #4-standardize-appointment-fields
        end_time = appointment_data.get("end_time")  # ToDo: #4-standardize-appointment-fields
        to_self_delay = appointment_data.get("to_self_delay")
        encrypted_blob_data = appointment_data.get("encrypted_blob")

        if any(v is None for v in [locator, start_time, end_time, to_self_delay, encrypted_blob_data]):
            raise ValueError("Wrong appointment data, some fields are missing")

        else:
            appointment = cls(locator, start_time, end_time, to_self_delay, encrypted_blob_data)

        return appointment

    def to_dict(self):
        """
        Exports an appointment as a dictionary.

        Returns:
            :obj:`dict`: A dictionary containing the appointment attributes.

        """

        # ToDO: #3-improve-appointment-structure
        appointment = {
            "locator": self.locator,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "to_self_delay": self.to_self_delay,
            "encrypted_blob": self.encrypted_blob.data,
        }

        return appointment

    def to_json(self):
        """
        Exports an appointment as a deterministic json encoded string.

        This method ensures that multiple invocations with the same data yield the same value. This is the format used
        to store appointments in the database.

        Returns:
            :obj:`str`: A json-encoded str representing the appointment.
        """

        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def serialize(self):
        """
        Serializes an appointment to be signed.

        The serialization follows the same ordering as the fields in the appointment:
            locator:start_time:end_time:to_self_delay:encrypted_blob

        All values are big endian.

        Returns:
              :mod:`bytes`: The serialized data to be signed.
        """
        return (
            unhexlify(self.locator)
            + struct.pack(">I", self.start_time)
            + struct.pack(">I", self.end_time)
            + struct.pack(">I", self.to_self_delay)
            + unhexlify(self.encrypted_blob.data)
        )
