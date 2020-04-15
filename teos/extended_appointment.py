from common.appointment import Appointment


class ExtendedAppointment(Appointment):
    def __init__(self, locator, to_self_delay, encrypted_blob, user_id):
        super().__init__(locator, to_self_delay, encrypted_blob)
        self.user_id = user_id

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

        if not user_id:
            raise ValueError("Wrong appointment data, user_id is missing")

        else:
            appointment = cls(appointment.locator, appointment.to_self_delay, appointment.encrypted_blob, user_id)

        return appointment
