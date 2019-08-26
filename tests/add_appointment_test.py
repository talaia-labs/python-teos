import os
import json
import requests
import time
from hashlib import sha256
from binascii import hexlify, unhexlify
from apps.cli.blob import Blob
from pisa import HOST, PORT
from pisa.utils.authproxy import AuthServiceProxy
from pisa.conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT

PISA_API = "http://{}:{}".format(HOST, PORT)


def generate_dummy_appointment(dispute_txid):
    r = requests.get(url=PISA_API+'/get_block_count', timeout=5)

    current_height = r.json().get("block_count")

    dummy_appointment_data = {"tx": hexlify(os.urandom(32)).decode('utf-8'),
                              "tx_id": dispute_txid, "start_time": current_height + 5,
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


dispute_txid = hexlify(os.urandom(32)).decode('utf-8')
appointment = generate_dummy_appointment(dispute_txid)

print("Sending appointment (locator: {}) to PISA".format(appointment.get("locator")))
r = requests.post(url=PISA_API, json=json.dumps(appointment), timeout=5)
print(r, r.reason, r.content)

print("Requesting it back from PISA")
r = requests.get(url=PISA_API+"/get_appointment?locator="+appointment["locator"])
print(r, r.reason, r.content)

time.sleep(2)
print("Sending it again")
appointment["end_time"] += 1
r = requests.post(url=PISA_API, json=json.dumps(appointment), timeout=5)
print(r, r.reason, r.content)

print("Sleeping 10 sec")
time.sleep(10)
bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT))

print("Getting all appointments")
r = requests.get(url=PISA_API+"/get_all_appointments")
print(r, r.reason, r.content)

print("Triggering PISA with dispute tx")
bitcoin_cli.sendrawtransaction(dispute_txid)

time.sleep(10)
print("Requesting it again")
r = requests.get(url=PISA_API+"/get_appointment?locator="+appointment["locator"])
print(r, r.reason, r.content)

print("Getting all appointments")
r = requests.get(url=PISA_API+"/get_all_appointments")
print(r, r.reason, r.content)