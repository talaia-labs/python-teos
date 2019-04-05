# Basic appointment structure
class Appointment:
    def __init__(self, locator, start_time, end_time, encrypted_blob, cypher):
        self.locator = locator
        self.start_time = start_time
        self.end_time = end_time
        self.encrypted_blob = encrypted_blob
        self.cypher = cypher


