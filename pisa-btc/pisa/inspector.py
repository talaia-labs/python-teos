from pisa.appointment import Appointment


class Inspector:
    def __init__(self):
        pass

    def inspect(self, appointment, debug):
        return Appointment(appointment, None, None, None, None)
