from common.appointment import Appointment


class ExtendedAppointment(Appointment):
    """
    The :class:`ExtendedAppointment` contains extended information about an appointment between a user and the tower.

    It extends the :class:`Appointment <common.appointment.Appointment>` with information relevant to the tower, such
    as the ``user_id``, ``user_signature`` and ``start_block``.

    **All appointments are instances of** :obj:`Appointment <common.appointment.Appointment>` **on the user-side but**
    :obj:`ExtendedAppointment` **on the tower-side.**

    Args:
        locator (:obj:`str`): A 16-byte hex-encoded value used by the tower to detect channel breaches. It serves as a
            trigger for the tower to decrypt and broadcast the penalty transaction.
        encrypted_blob (:obj:`str`): An encrypted blob of data containing a penalty transaction. The tower will decrypt
            it and broadcast the penalty transaction upon seeing a breach on the blockchain.
        to_self_delay (:obj:`int`): The ``to_self_delay`` encoded in the ``csv`` of the ``to_remote`` output of the
            commitment transaction that this appointment is covering.
        user_id (:obj:`str`): the public key that identifies the user (33-bytes hex str).
        user_signature (:obj:`str`): the signature of the appointment by the user.
        start_block (:obj:`str`): the block height at where the towers started watching for this appointment.
    """

    def __init__(self, locator, encrypted_blob, to_self_delay, user_id, user_signature, start_block):
        super().__init__(locator, encrypted_blob, to_self_delay)
        self.user_id = user_id
        self.user_signature = user_signature
        self.start_block = start_block

    def get_summary(self):
        """
        Returns the summary of an appointment, consisting on the ``locator``, and the ``user_id``.

        Returns:
            :obj:`dict`: The appointment summary.
        """
        return {"locator": self.locator, "user_id": self.user_id}

    @classmethod
    def from_dict(cls, appointment_data):
        """
        Builds an appointment from a dictionary.

        This method is useful to load data from a database.

        Args:
            appointment_data (:obj:`dict`): a dictionary containing the following keys:
                ``{locator, to_self_delay, encrypted_blob, user_id}``

        Returns:
            :obj:`ExtendedAppointment <teos.extended_appointment.ExtendedAppointment>`: An appointment initialized
            using the provided data.

        Raises:
            ValueError: If one of the mandatory keys is missing in ``appointment_data``.
        """

        appointment = Appointment.from_dict(appointment_data)
        user_id = appointment_data.get("user_id")
        user_signature = appointment_data.get("user_signature")
        start_block = appointment_data.get("start_block")

        if any(v is None for v in [user_id, user_signature, start_block]):
            raise ValueError("Wrong appointment data, some fields are missing")

        return cls(
            appointment.locator,
            appointment.encrypted_blob,
            appointment.to_self_delay,
            user_id,
            user_signature,
            start_block,
        )
