class TowerInfo:
    def __init__(self, netaddr, available_slots, appointments=None):
        self.netaddr = netaddr
        self.available_slots = available_slots

        if not appointments:
            self.appointments = {}
        else:
            self.appointments = appointments

    @classmethod
    def from_dict(cls, tower_data):
        netaddr = tower_data.get("netaddr")
        available_slots = tower_data.get("available_slots")
        appointments = tower_data.get("appointments")

        if any(v is None for v in [netaddr, available_slots, appointments]):
            raise ValueError("Wrong appointment data, some fields are missing")

        return cls(netaddr, available_slots, appointments)

    def to_dict(self):
        return self.__dict__

    def get_summary(self):
        return {"netaddr": self.netaddr, "available_slots": self.available_slots}
