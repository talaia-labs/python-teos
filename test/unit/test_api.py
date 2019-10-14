import os
import json
import pytest
import time
import requests
from hashlib import sha256
from binascii import unhexlify

from apps.cli.blob import Blob
from pisa import HOST, PORT, logging
from pisa.utils.auth_proxy import AuthServiceProxy
from test.simulator.bitcoind_sim import TIME_BETWEEN_BLOCKS
from pisa.conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT, MAX_APPOINTMENTS

logging.getLogger().disabled = True
PISA_API = "http://{}:{}".format(HOST, PORT)
MULTIPLE_APPOINTMENTS = 10

appointments = []
locator_dispute_txid_map = {}


def generate_dummy_appointment(dispute_txid):
    r = requests.get(url=PISA_API + '/get_block_count', timeout=5)

    current_height = r.json().get("block_count")

    dummy_appointment_data = {"tx": os.urandom(32).hex(), "tx_id": dispute_txid, "start_time": current_height + 5,
                              "end_time": current_height + 30, "dispute_delta": 20}

    cipher = "AES-GCM-128"
    hash_function = "SHA256"

    locator = sha256(unhexlify(dummy_appointment_data.get("tx_id"))).hexdigest()
    blob = Blob(dummy_appointment_data.get("tx"), cipher, hash_function)

    encrypted_blob = blob.encrypt((dummy_appointment_data.get("tx_id")))

    appointment = {"locator": locator, "start_time": dummy_appointment_data.get("start_time"),
                   "end_time": dummy_appointment_data.get("end_time"),
                   "dispute_delta": dummy_appointment_data.get("dispute_delta"),
                   "encrypted_blob": encrypted_blob, "cipher": cipher, "hash_function": hash_function}

    return appointment


@pytest.fixture
def new_appointment(dispute_txid=None):
    appointment = create_appointment(dispute_txid)

    return appointment


def create_appointment(dispute_txid=None):
    if dispute_txid is None:
        dispute_txid = os.urandom(32).hex()

    appointment = generate_dummy_appointment(dispute_txid)
    locator_dispute_txid_map[appointment["locator"]] = dispute_txid

    return appointment


def add_appointment(appointment):
    r = requests.post(url=PISA_API, json=json.dumps(appointment), timeout=5)

    if r.status_code == 200:
        appointments.append(appointment)

    return r


def test_add_appointment(run_api, run_bitcoind, new_appointment):
    # Properly formatted appointment
    r = add_appointment(new_appointment)
    assert (r.status_code == 200)

    # Incorrect appointment
    new_appointment["dispute_delta"] = 0
    r = add_appointment(new_appointment)
    assert (r.status_code == 400)


def test_request_appointment(new_appointment):
    # First we need to add an appointment
    r = add_appointment(new_appointment)
    assert (r.status_code == 200)

    # Next we can request it
    r = requests.get(url=PISA_API + "/get_appointment?locator=" + new_appointment["locator"])
    assert (r.status_code == 200)

    # Each locator may point to multiple appointments, check them all
    received_appointments = json.loads(r.content)

    # Take the status out and leave the received appointments ready to compare
    appointment_status = [appointment.pop("status") for appointment in received_appointments]

    # Check that the appointment is within the received appoints
    assert (new_appointment in received_appointments)

    # Check that all the appointments are being watched
    assert (all([status == "being_watched" for status in appointment_status]))


def test_add_appointment_multiple_times(new_appointment, n=MULTIPLE_APPOINTMENTS):
    # Multiple appointments with the same locator should be valid
    # DISCUSS: #34-store-identical-appointments
    for _ in range(n):
        r = add_appointment(new_appointment)
        assert (r.status_code == 200)


def test_request_multiple_appointments_same_locator(new_appointment, n=MULTIPLE_APPOINTMENTS):
    for _ in range(n):
        r = add_appointment(new_appointment)
        assert (r.status_code == 200)

    test_request_appointment(new_appointment)


def test_add_too_many_appointment(new_appointment):
    for _ in range(MAX_APPOINTMENTS-len(appointments)):
        r = add_appointment(new_appointment)
        assert (r.status_code == 200)

    r = add_appointment(new_appointment)
    assert (r.status_code == 503)


def test_get_all_appointments_watcher():
    r = requests.get(url=PISA_API + "/get_all_appointments")
    assert (r.status_code == 200 and r.reason == 'OK')

    received_appointments = json.loads(r.content)

    # Make sure there all the locators re in the watcher
    watcher_locators = [v["locator"] for k, v in received_appointments["watcher_appointments"].items()]
    local_locators = [appointment["locator"] for appointment in appointments]

    assert(set(watcher_locators) == set(local_locators))
    assert(len(received_appointments["responder_jobs"]) == 0)


def test_get_all_appointments_responder():
    # Trigger all disputes
    bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT))

    locators = [appointment["locator"] for appointment in appointments]
    for locator, dispute_txid in locator_dispute_txid_map.items():
        if locator in locators:
            bitcoin_cli.sendrawtransaction(dispute_txid)

    # Wait a bit for them to get confirmed
    time.sleep(TIME_BETWEEN_BLOCKS)

    # Get all appointments
    r = requests.get(url=PISA_API + "/get_all_appointments")
    received_appointments = json.loads(r.content)

    # Make sure there is not pending locator in the watcher
    responder_jobs = [v["locator"] for k, v in received_appointments["responder_jobs"].items()]
    local_locators = [appointment["locator"] for appointment in appointments]

    assert (set(responder_jobs) == set(local_locators))
    assert (len(received_appointments["watcher_appointments"]) == 0)
