import re


class Blob:
    def __init__(self, data):
        if type(data) is not str or re.search(r"^[0-9A-Fa-f]+$", data) is None:
            raise ValueError("Non-Hex character found in transaction.")

        self.data = data
