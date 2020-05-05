class TowerInfo:
    def __init__(self, netaddr, available_slots, status="reachable"):
        self.netaddr = netaddr
        self.available_slots = available_slots
        self.status = status

        self.appointments = {}
        self.pending_appointments = []
        self.invalid_appointments = []
        self.misbehaving_proof = None

    @classmethod
    def from_dict(cls, tower_data):
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
        return self.__dict__

    def get_summary(self):
        return TowerSummary(self)


class TowerSummary:
    def __init__(self, tower_info):
        self.netaddr = tower_info.netaddr
        self.status = tower_info.status
        self.available_slots = tower_info.available_slots
        self.pending_appointments = tower_info.pending_appointments
        self.invalid_appointments = tower_info.invalid_appointments

    def to_dict(self):
        return self.__dict__
