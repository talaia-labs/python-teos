class TowerInfo:
    def __init__(
        self,
        netaddr,
        available_slots,
        status="reachable",
        appointments=None,
        pending_appointments=None,
        invalid_appointments=None,
    ):

        self.netaddr = netaddr
        self.available_slots = available_slots
        self.status = status

        if not appointments:
            self.appointments = {}
        else:
            self.appointments = appointments

        if not pending_appointments:
            self.pending_appointments = []
        else:
            self.pending_appointments = pending_appointments

        if not invalid_appointments:
            self.invalid_appointments = []
        else:
            self.invalid_appointments = invalid_appointments

    @classmethod
    def from_dict(cls, tower_data):
        netaddr = tower_data.get("netaddr")
        available_slots = tower_data.get("available_slots")
        status = tower_data.get("status")
        appointments = tower_data.get("appointments")
        pending_appointments = tower_data.get("pending_appointments")
        invalid_appointments = tower_data.get("invalid_appointments")

        if any(
            v is None
            for v in [netaddr, available_slots, status, appointments, pending_appointments, invalid_appointments]
        ):
            raise ValueError("Wrong appointment data, some fields are missing")

        return cls(netaddr, available_slots, status, appointments, pending_appointments, invalid_appointments)

    def to_dict(self):
        return self.__dict__

    def get_summary(self):
        return {
            "netaddr": self.netaddr,
            "status": self.status,
            "available_slots": self.available_slots,
            "pending_appointments": self.pending_appointments,
            "invalid_appointments": self.invalid_appointments,
        }
