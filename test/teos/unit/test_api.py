import json
import pytest
import requests
from time import sleep
from threading import Thread

from teos.api import API
from teos import HOST, PORT
from teos.watcher import Watcher
from teos.tools import bitcoin_cli
from teos.inspector import Inspector
from teos.responder import Responder
from teos.gatekeeper import Gatekeeper
from teos.chain_monitor import ChainMonitor

from test.teos.unit.conftest import (
    generate_block,
    generate_blocks,
    get_random_value_hex,
    generate_dummy_appointment_data,
    generate_keypair,
    get_config,
    bitcoind_connect_params,
    bitcoind_feed_params,
)


from common.constants import LOCATOR_LEN_BYTES


TEOS_API = "http://{}:{}".format(HOST, PORT)
add_appointment_endpoint = "{}/add_appointment".format(TEOS_API)
get_appointment_endpoint = "{}/get_appointment".format(TEOS_API)
get_all_appointment_endpoint = "{}/get_all_appointments".format(TEOS_API)

MULTIPLE_APPOINTMENTS = 10

appointments = []
locator_dispute_tx_map = {}

config = get_config()


@pytest.fixture(scope="module")
def run_api(db_manager, carrier, block_processor):
    sk, pk = generate_keypair()

    responder = Responder(db_manager, carrier, block_processor)
    watcher = Watcher(
        db_manager, block_processor, responder, sk.to_der(), config.get("MAX_APPOINTMENTS"), config.get("EXPIRY_DELTA")
    )

    chain_monitor = ChainMonitor(
        watcher.block_queue, watcher.responder.block_queue, block_processor, bitcoind_feed_params
    )
    watcher.awake()
    chain_monitor.monitor_chain()

    api_thread = Thread(
        target=API(Inspector(block_processor, config.get("MIN_TO_SELF_DELAY")), watcher, Gatekeeper()).start
    )
    api_thread.daemon = True
    api_thread.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)


@pytest.fixture
def new_appt_data():
    appt_data, dispute_tx = generate_dummy_appointment_data()
    locator_dispute_tx_map[appt_data["appointment"]["locator"]] = dispute_tx

    return appt_data


def add_appointment(new_appt_data):
    r = requests.post(url=add_appointment_endpoint, json=new_appt_data, timeout=5)

    if r.status_code == 200:
        appointments.append(new_appt_data["appointment"])

    return r


def test_add_appointment(run_api, run_bitcoind, new_appt_data):
    # Properly formatted appointment
    r = add_appointment(new_appt_data)
    assert r.status_code == 200

    # Incorrect appointment
    new_appt_data["appointment"]["to_self_delay"] = 0
    r = add_appointment(new_appt_data)
    assert r.status_code == 400


def test_request_random_appointment():
    r = requests.get(url="{}?locator={}".format(get_appointment_endpoint, get_random_value_hex(LOCATOR_LEN_BYTES)))
    assert r.status_code == 200

    received_appointments = json.loads(r.content)
    appointment_status = [appointment.pop("status") for appointment in received_appointments]

    assert all([status == "not_found" for status in appointment_status])


def test_add_appointment_multiple_times(new_appt_data, n=MULTIPLE_APPOINTMENTS):
    # Multiple appointments with the same locator should be valid
    # DISCUSS: #34-store-identical-appointments
    for _ in range(n):
        r = add_appointment(new_appt_data)
        assert r.status_code == 200


def test_request_multiple_appointments_same_locator(new_appt_data, n=MULTIPLE_APPOINTMENTS):
    for _ in range(n):
        r = add_appointment(new_appt_data)
        assert r.status_code == 200

    test_request_appointment_watcher(new_appt_data)


def test_add_too_many_appointment(new_appt_data):
    for _ in range(config.get("MAX_APPOINTMENTS") - len(appointments)):
        r = add_appointment(new_appt_data)
        assert r.status_code == 200

    r = add_appointment(new_appt_data)
    assert r.status_code == 503


def test_get_all_appointments_watcher():
    r = requests.get(url=get_all_appointment_endpoint)
    assert r.status_code == 200 and r.reason == "OK"

    received_appointments = json.loads(r.content)

    # Make sure there all the locators re in the watcher
    watcher_locators = [v["locator"] for k, v in received_appointments["watcher_appointments"].items()]
    local_locators = [appointment["locator"] for appointment in appointments]

    assert set(watcher_locators) == set(local_locators)
    assert len(received_appointments["responder_trackers"]) == 0


def test_get_all_appointments_responder():
    # Trigger all disputes
    locators = [appointment["locator"] for appointment in appointments]
    for locator, dispute_tx in locator_dispute_tx_map.items():
        if locator in locators:
            bitcoin_cli(bitcoind_connect_params).sendrawtransaction(dispute_tx)

    # Confirm transactions
    generate_blocks(6)

    # Get all appointments
    r = requests.get(url=get_all_appointment_endpoint)
    received_appointments = json.loads(r.content)

    # Make sure there is not pending locator in the watcher
    responder_trackers = [v["locator"] for k, v in received_appointments["responder_trackers"].items()]
    local_locators = [appointment["locator"] for appointment in appointments]

    assert set(responder_trackers) == set(local_locators)
    assert len(received_appointments["watcher_appointments"]) == 0


def test_request_appointment_watcher(new_appt_data):
    # First we need to add an appointment
    r = add_appointment(new_appt_data)
    assert r.status_code == 200

    # Next we can request it
    r = requests.get(url="{}?locator={}".format(get_appointment_endpoint, new_appt_data["appointment"]["locator"]))
    assert r.status_code == 200

    # Each locator may point to multiple appointments, check them all
    received_appointments = json.loads(r.content)

    # Take the status out and leave the received appointments ready to compare
    appointment_status = [appointment.pop("status") for appointment in received_appointments]

    # Check that the appointment is within the received appointments
    assert new_appt_data["appointment"] in received_appointments

    # Check that all the appointments are being watched
    assert all([status == "being_watched" for status in appointment_status])


def test_request_appointment_responder(new_appt_data):
    # Let's do something similar to what we did with the watcher but now we'll send the dispute tx to the network
    dispute_tx = locator_dispute_tx_map[new_appt_data["appointment"]["locator"]]
    bitcoin_cli(bitcoind_connect_params).sendrawtransaction(dispute_tx)

    r = add_appointment(new_appt_data)
    assert r.status_code == 200

    # Generate a block to trigger the watcher
    generate_block()

    r = requests.get(url="{}?locator={}".format(get_appointment_endpoint, new_appt_data["appointment"]["locator"]))
    assert r.status_code == 200

    received_appointments = json.loads(r.content)
    appointment_status = [appointment.pop("status") for appointment in received_appointments]
    appointment_locators = [appointment["locator"] for appointment in received_appointments]

    assert new_appt_data["appointment"]["locator"] in appointment_locators and len(received_appointments) == 1
    assert all([status == "dispute_responded" for status in appointment_status]) and len(appointment_status) == 1
