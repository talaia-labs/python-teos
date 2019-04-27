from pisa.appointment import Appointment


# FIXME: Implement a proper inspector
class Inspector:
    def __init__(self):
        pass

    def inspect(self, appointment, debug):
        # Return Appointment if success, None otherwise
        return Appointment(appointment, None, None, None, None, None)
