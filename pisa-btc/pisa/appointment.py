

# Basic appointment structure
class Appointment:
    def __init__(self, locator, start_time, end_time, dispute_delta, encrypted_blob, cypher):
        self.locator = locator
        self.start_time = start_time
        self.end_time = end_time
        self.dispute_delta = dispute_delta
        self.encrypted_blob = encrypted_blob
        self.cipher = cypher


