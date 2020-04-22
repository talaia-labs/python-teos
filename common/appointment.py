import struct
from binascii import unhexlify


class Appointment:
    """
    The :class:`Appointment` contains the information regarding an appointment between a client and the Watchtower.

    Args:
        locator (:obj:`str`): A 16-byte hex-encoded value used by the tower to detect channel breaches. It serves as a
            trigger for the tower to decrypt and broadcast the penalty transaction.
        to_self_delay (:obj:`int`): The ``to_self_delay`` encoded in the ``csv`` of the ``to_remote`` output of the
            commitment transaction that this appointment is covering.
        encrypted_blob (:obj:`str`): An encrypted blob of data containing a penalty transaction. The tower will decrypt
            it and broadcast the penalty transaction upon seeing a breach on the blockchain.
    """

    def __init__(self, locator, to_self_delay, encrypted_blob):
        self.locator = locator
        self.to_self_delay = to_self_delay
        self.encrypted_blob = encrypted_blob

    @classmethod
    def from_dict(cls, appointment_data):
        """
        Builds an appointment from a dictionary.

        Args:
            appointment_data (:obj:`dict`): a dictionary containing the following keys:
                ``{locator, to_self_delay, encrypted_blob}``

        Returns:
            :obj:`Appointment <common.appointment.Appointment>`: An appointment initialized using the provided data.

        Raises:
            ValueError: If one of the mandatory keys is missing in ``appointment_data``.
        """

        locator = appointment_data.get("locator")
        to_self_delay = appointment_data.get("to_self_delay")
        encrypted_blob = appointment_data.get("encrypted_blob")

        if any(v is None for v in [locator, to_self_delay, encrypted_blob]):
            raise ValueError("Wrong appointment data, some fields are missing")

        else:
            appointment = cls(locator, to_self_delay, encrypted_blob)

        return appointment

    def to_dict(self):
        """
        Encodes an appointment as a dictionary.

        Returns:
            :obj:`dict`: A dictionary containing the appointment attributes.
        """

        return self.__dict__

    def serialize(self):
        """
        Serializes an appointment to be signed.

        The serialization follows the same ordering as the fields in the appointment:
            locator:to_self_delay:encrypted_blob

        All values are big endian.

        Returns:
              :obj:`bytes`: The serialized data to be signed.
        """
        return unhexlify(self.locator) + struct.pack(">I", self.to_self_delay) + unhexlify(self.encrypted_blob)
