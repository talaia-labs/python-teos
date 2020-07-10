class TowerInfo:
    """
    TowerInfo represents all the data the plugin hold about a tower.

    Args:
        netaddr (:obj:`str`): the tower network address.
        available_slots (:obj:`int`): the amount of available appointment slots in the tower.
        status (:obj:`str`): the tower status. The tower can be in the following status:
            reachable: if the tower can be reached.
            temporarily unreachable: if the tower cannot be reached but the issue is transitory.
            unreachable: if the tower cannot be reached and the issue has persisted long enough, or it is permanent.
            subscription error: if there has been a problem with the subscription (e.g: run out of slots).
            misbehaving: if the tower has been caught misbehaving (e.g: an invalid signature has been received).

    Attributes:
        appointments (:obj:`dict`): a collection of accepted appointments.
        pending_appointments (:obj:`list`): a collection of pending appointments. Appointments are pending when the
            tower is unreachable or the subscription has expired / run out of slots.
        invalid_appointments (:obj:`list`): a collection of invalid appointments. Appointments are invalid if the tower
            rejects them for not following the proper format.
        misbehaving_proof (:obj:`dict`): a proof of misbehaviour from the tower. The tower is abandoned if so.
    """

    def __init__(self, netaddr, available_slots, status="reachable"):
        self.netaddr = netaddr
        self.available_slots = available_slots
        self.status = status

        self.appointments = {}
        self.pending_appointments = []
        self.invalid_appointments = []
        self.misbehaving_proof = {}

    @classmethod
    def from_dict(cls, tower_data):
        """
        Builds a TowerInfo object from a dictionary.

        Args:
            tower_data (:obj:`dict`): a dictionary containing all the TowerInfo fields.

        Returns:
            :obj:`TowerInfo`: A TowerInfo object built with the provided data.

        Raises:
            :obj:`ValueError`: If any of the expected fields is missing in the dictionary.
        """

        netaddr = tower_data.get("netaddr")
        available_slots = tower_data.get("available_slots")
        status = tower_data.get("status")
        appointments = tower_data.get("appointments")
        pending_appointments = tower_data.get("pending_appointments")
        invalid_appointments = tower_data.get("invalid_appointments")
        misbehaving_proof = tower_data.get("misbehaving_proof")

        if any(
            v is None
            for v in [netaddr, available_slots, status, appointments, pending_appointments, invalid_appointments]
        ):
            raise ValueError("Wrong appointment data, some fields are missing")

        tower = cls(netaddr, available_slots, status)
        tower.appointments = appointments
        tower.pending_appointments = pending_appointments
        tower.invalid_appointments = invalid_appointments
        tower.misbehaving_proof = misbehaving_proof

        return tower

    def to_dict(self):
        """
        Builds a dictionary from a TowerInfo object.

        Returns:
            :obj:`dict`: The TowerInfo object as a dictionary.
        """
        return self.__dict__

    def get_summary(self):
        """
        Gets a summary of the TowerInfo object.

        The plugin only stores the minimal information in memory, the rest is dumped into the DB. Data kept in memory
        is stored in TowerSummary objects.

        Returns:
            :obj:`dict`: The summary of the TowerInfo object.
        """
        return TowerSummary(self)


class TowerSummary:
    """
    A smaller representation of the TowerInfo data to be kept in memory.

    Args:
        tower_info(:obj:`TowerInfo`): A TowerInfo object.

    Attributes:
        netaddr (:obj:`str`): the tower network address.
        status (:obj:`str`): the status of the tower.
        available_slots (:obj:`int`): the amount of available appointment slots in the tower.
        pending_appointments (:obj:`list`): the collection of pending appointments.
        invalid_appointments (:obj:`list`): the collection of invalid appointments.
    """

    def __init__(self, tower_info):
        self.netaddr = tower_info.netaddr
        self.status = tower_info.status
        self.available_slots = tower_info.available_slots
        self.pending_appointments = tower_info.pending_appointments
        self.invalid_appointments = tower_info.invalid_appointments

    def to_dict(self):
        """
        Builds a dictionary from a TowerSummary object.

        Returns:
            :obj:`dict`: The TowerSummary object as a dictionary.
        """

        return self.__dict__
