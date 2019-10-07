import os
import json
import time
import requests
from copy import deepcopy
from hashlib import sha256
from binascii import unhexlify

from pisa import HOST, PORT
from apps.cli.blob import Blob
from pisa.utils.auth_proxy import AuthServiceProxy
from pisa.conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT

PISA_API = "http://{}:{}".format(HOST, PORT)


def generate_dummy_appointment(dispute_txid):
    r = requests.get(url=PISA_API + '/get_block_count', timeout=5)

    current_height = r.json().get("block_count")

    dummy_appointment_data = {"tx": os.urandom(32).hex(), "tx_id": dispute_txid, "start_time": current_height + 5,
                              "end_time": current_height + 10, "dispute_delta": 20}

    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    locator = sha256(unhexlify(dummy_appointment_data.get("tx_id"))).hexdigest()
    blob = Blob(dummy_appointment_data.get("tx"), cipher, hash_function)

    encrypted_blob = blob.encrypt((dummy_appointment_data.get("tx_id")), debug=False, logging=False)

    appointment = {"locator": locator, "start_time": dummy_appointment_data.get("start_time"),
                   "end_time": dummy_appointment_data.get("end_time"),
                   "dispute_delta": dummy_appointment_data.get("dispute_delta"),
                   "encrypted_blob": encrypted_blob, "cipher": cipher, "hash_function": hash_function}

    return appointment


def test_add_appointment(appointment=None):
    if not appointment:
        dispute_txid = os.urandom(32).hex()
        appointment = generate_dummy_appointment(dispute_txid)

    print("Sending appointment (locator: {}) to PISA".format(appointment.get("locator")))
    r = requests.post(url=PISA_API, json=json.dumps(appointment), timeout=5)

    assert (r.status_code == 200 and r.reason == 'OK')
    print(r.content.decode())

    print("Requesting it back from PISA")
    r = requests.get(url=PISA_API + "/get_appointment?locator=" + appointment["locator"])

    assert (r.status_code == 200 and r.reason == 'OK')

    received_appointments = json.loads(r.content)

    # Take the status out and leave the received appointments ready to compare
    appointment_status = [appointment.pop("status") for appointment in received_appointments]

    # Check that the appointment is within the received appoints
    assert (appointment in received_appointments)

    # Check that all the appointments are being watched
    assert (all([status == "being_watched" for status in appointment_status]))


def test_same_locator_multiple_appointments():
    dispute_txid = os.urandom(32).hex()
    appointment = generate_dummy_appointment(dispute_txid)

    # Send it once
    test_add_appointment(appointment)
    time.sleep(0.5)

    # Try again with the same data
    print("Sending it again")
    test_add_appointment(appointment)
    time.sleep(0.5)

    # Try again with the same data but increasing the end time
    print("Sending once more")
    dup_appointment = deepcopy(appointment)
    dup_appointment["end_time"] += 1
    test_add_appointment(dup_appointment)

    print("Sleeping 5 sec")
    time.sleep(5)

    bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT))

    print("Triggering PISA with dispute tx")
    bitcoin_cli.sendrawtransaction(dispute_txid)

    print("Sleeping 10 sec (waiting for a new block)")
    time.sleep(10)

    print("Getting all appointments")
    r = requests.get(url=PISA_API + "/get_all_appointments")

    assert (r.status_code == 200 and r.reason == 'OK')

    received_appointments = json.loads(r.content)

    # Make sure there is not pending instance of the locator in the watcher
    watcher_locators = [appointment["locator"] for appointment in received_appointments["watcher_appointments"]]
    assert(appointment["locator"] not in watcher_locators)

    # Make sure all the appointments went trough
    target_jobs = [v for k, v in received_appointments["responder_jobs"].items() if v["locator"] ==
                   appointment["locator"]]

    assert (len(target_jobs) == 3)
    

if __name__ == '__main__':

    test_same_locator_multiple_appointments()

    print("All good!")
