import pisa.conf as conf
from pisa.inspector import Inspector
from pisa.appointment import Appointment
from pisa import errors, logging, bitcoin_cli
from pisa.utils.auth_proxy import JSONRPCException

appointment = {"locator": None, "start_time": None, "end_time": None, "dispute_delta": None,
               "encrypted_blob": None, "cipher": None, "hash_function": None}

try:
    block_height = bitcoin_cli.getblockcount()

except JSONRPCException as e:
    logging.error("[Inspector] JSONRPCException. Error code {}".format(e))

locators = [None, 0, 'A' * 31, "A" * 63 + "_"]
start_times = [None, 0, '', 15.0, block_height - 10]
end_times = [None, 0, '', 26.123, block_height - 11]
dispute_deltas = [None, 0, '', 1.2, -3, 30]
encrypted_blobs = [None, 0, '']
ciphers = [None, 0, '', 'foo']
hash_functions = [None, 0, '', 'foo']

locators_rets = [errors.APPOINTMENT_EMPTY_FIELD, errors.APPOINTMENT_WRONG_FIELD_TYPE,
                 errors.APPOINTMENT_WRONG_FIELD_SIZE, errors.APPOINTMENT_WRONG_FIELD_FORMAT]

start_time_rets = [errors.APPOINTMENT_EMPTY_FIELD, errors.APPOINTMENT_FIELD_TOO_SMALL,
                   errors.APPOINTMENT_WRONG_FIELD_TYPE, errors.APPOINTMENT_WRONG_FIELD_TYPE,
                   errors.APPOINTMENT_FIELD_TOO_SMALL]

end_time_rets = [errors.APPOINTMENT_EMPTY_FIELD, errors.APPOINTMENT_FIELD_TOO_SMALL,
                 errors.APPOINTMENT_WRONG_FIELD_TYPE, errors.APPOINTMENT_WRONG_FIELD_TYPE,
                 errors.APPOINTMENT_FIELD_TOO_SMALL]

dispute_delta_rets = [errors.APPOINTMENT_EMPTY_FIELD, errors.APPOINTMENT_FIELD_TOO_SMALL,
                      errors.APPOINTMENT_WRONG_FIELD_TYPE, errors.APPOINTMENT_WRONG_FIELD_TYPE,
                      errors.APPOINTMENT_FIELD_TOO_SMALL]

encrypted_blob_rets = [errors.APPOINTMENT_EMPTY_FIELD, errors.APPOINTMENT_WRONG_FIELD_TYPE,
                       errors.APPOINTMENT_WRONG_FIELD]

cipher_rets = [errors.APPOINTMENT_EMPTY_FIELD, errors.APPOINTMENT_WRONG_FIELD_TYPE,
               errors.APPOINTMENT_CIPHER_NOT_SUPPORTED, errors.APPOINTMENT_CIPHER_NOT_SUPPORTED]

hash_function_rets = [errors.APPOINTMENT_EMPTY_FIELD, errors.APPOINTMENT_WRONG_FIELD_TYPE,
                      errors.APPOINTMENT_HASH_FUNCTION_NOT_SUPPORTED, errors.APPOINTMENT_HASH_FUNCTION_NOT_SUPPORTED]

inspector = Inspector()

print("Locator tests\n")
for locator, ret in zip(locators, locators_rets):
    appointment["locator"] = locator
    r = inspector.inspect(appointment)

    assert r[0] == ret
    print(r)

# Set locator to a 'valid' one
appointment['locator'] = 'A' * 64

print("\nStart time tests\n")
for start_time, ret in zip(start_times, start_time_rets):
    appointment["start_time"] = start_time
    r = inspector.inspect(appointment)

    assert r[0] == ret
    print(r)
# Setting the start time to some time in the future
appointment['start_time'] = block_height + 10

print("\nEnd time tests\n")
for end_time, ret in zip(end_times, end_time_rets):
    appointment["end_time"] = end_time
    r = inspector.inspect(appointment)

    assert r[0] == ret
    print(r)

# Setting the end time to something consistent with start time
appointment['end_time'] = block_height + 30

print("\nDelta tests\n")
for dispute_delta, ret in zip(dispute_deltas, dispute_delta_rets):
    appointment["dispute_delta"] = dispute_delta
    r = inspector.inspect(appointment)

    assert r[0] == ret
    print(r)

# Setting the a proper dispute delta
appointment['dispute_delta'] = appointment['end_time'] - appointment['start_time']

print("\nEncrypted blob tests\n")
for encrypted_blob, ret in zip(encrypted_blobs, encrypted_blob_rets):
    appointment["encrypted_blob"] = encrypted_blob
    r = inspector.inspect(appointment)

    assert r[0] == ret
    print(r)

# Setting the encrypted blob to something that may pass
appointment['encrypted_blob'] = 'A' * 32

print("\nCipher tests\n")
for cipher, ret in zip(ciphers, cipher_rets):
    appointment["cipher"] = cipher
    r = inspector.inspect(appointment)

    assert r[0] == ret
    print(r)

# Setting the cipher to the only supported one for now
appointment['cipher'] = conf.SUPPORTED_CIPHERS[0]

print("\nHash function tests\n")
for hash_function, ret in zip(hash_functions, hash_function_rets):
    appointment["hash_function"] = hash_function
    r = inspector.inspect(appointment)

    assert r[0] == ret
    print(r)

# Setting the cipher to the only supported one for now
appointment['hash_function'] = conf.SUPPORTED_HASH_FUNCTIONS[0]

r = inspector.inspect(appointment)
assert type(r) == Appointment

print("\nAll tests passed!")

