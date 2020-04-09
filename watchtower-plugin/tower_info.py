class TowerInfo:
    def __init__(self, endpoint, available_slots, appointments=None):
        self.endpoint = endpoint
        self.available_slots = available_slots

        if not appointments:
            self.appointments = {}
        else:
            self.appointments = appointments

    @classmethod
    def from_dict(cls, tower_data):
        endpoint = tower_data.get("endpoint")
        available_slots = tower_data.get("available_slots")
        appointments = tower_data.get("appointments")

        if any(v is None for v in [endpoint, available_slots, appointments]):
            raise ValueError("Wrong appointment data, some fields are missing")

        return cls(endpoint, available_slots, appointments)

    def to_dict(self):
        return self.__dict__
