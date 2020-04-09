class TowerInfo:
    def __init__(self, endpoint, available_slots):
        self.endpoint = endpoint
        self.available_slots = available_slots

    @classmethod
    def from_dict(cls, tower_data):
        endpoint = tower_data.get("endpoint")
        available_slots = tower_data.get("available_slots")

        if any(v is None for v in [endpoint, available_slots]):
            raise ValueError("Wrong appointment data, some fields are missing")
        if available_slots is None:
            raise ValueError("Wrong tower data, some fields are missing")

        return cls(endpoint, available_slots)

    def to_dict(self):
        return self.__dict__
