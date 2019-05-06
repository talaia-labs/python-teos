from pisa.appointment import Appointment


class Inspector:
    def __init__(self):
        pass

    def inspect(self, data, debug):
        # TODO: We need to define standard names for the json fields, using Paddy's ones for now

        appointment = None

        locator = data.get('txlocator')
        start_time = data.get('startblock')
        end_time = data.get('endblock')

        # Missing for now
        dispute_delta = data.get('dispute_delta')

        # FIXME: this will be eventually be replaced, here for testing now
        encrypted_blob = data.get('rawtx')
        # encrypted_blob = data.get('encrypted_blob')

        cipher = data.get('cipher')

        if self.check_locator(locator, debug) and self.check_start_time(start_time, debug) and \
                self.check_end_time(end_time, debug) and self.check_delta(dispute_delta, debug) and \
                self.check_blob(encrypted_blob, debug) and self.check_cipher(cipher, debug):
            appointment = Appointment(locator, start_time, end_time, dispute_delta, encrypted_blob, cipher)

        return appointment

    # FIXME: Define checks
    def check_locator(self, locator, debug):
        return True

    def check_start_time(self, start_time, debug):
        return True

    def check_end_time(self, end_time, debug):
        return True

    def check_delta(self, dispute_delta, debug):
        return True

    def check_blob(self, encrypted_blob, debug):
        return True

    def check_cipher(self, cipher, debug):
        return True
