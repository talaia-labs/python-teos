from pisa.appointment import Appointment


class Inspector:
    def __init__(self):
        pass

    def inspect(self, data, debug):
        # TODO: We need to define standard names for the json fields, using Paddy's ones for now

        appointment = None

        locator = data.get('locator')
        start_time = data.get('start_block')
        end_time = data.get('end_block')
        dispute_delta = data.get('dispute_delta')
        encrypted_blob = data.get('encrypted_blob')
        cipher = data.get('cipher')
        hash_function = data.get('hash_function')

        if self.check_locator(locator, debug) and self.check_start_time(start_time, debug) and \
                self.check_end_time(end_time, debug) and self.check_delta(dispute_delta, debug) and \
                self.check_blob(encrypted_blob, debug) and self.check_cipher(cipher, debug) and \
                self.check_cipher(hash_function, debug):
            appointment = Appointment(locator, start_time, end_time, dispute_delta, encrypted_blob, cipher,
                                      hash_function)

        return appointment

    # FIXME: Define checks
    def check_locator(self, locator, debug):
        return locator is not None

    def check_start_time(self, start_time, debug):
        return start_time is not None

    def check_end_time(self, end_time, debug):
        return end_time is not None

    def check_delta(self, dispute_delta, debug):
        return dispute_delta is not None

    def check_blob(self, encrypted_blob, debug):
        return encrypted_blob is not None

    def check_cipher(self, cipher, debug):
        return cipher is not None

    def check_hash_function(self, hash_function, debug):
        return hash_function is not None
