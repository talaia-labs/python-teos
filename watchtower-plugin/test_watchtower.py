import random
import configparser
from time import sleep
from coincurve import PrivateKey
from threading import Thread
from flask import Flask, request, jsonify
from pyln.testing.fixtures import *  # noqa: F401,F403

from common import errors
from common import constants
import common.receipts as receipts
from common.appointment import Appointment
from common.cryptographer import Cryptographer

plugin_path = os.path.join(os.path.dirname(__file__), "watchtower.py")

tower_netaddr = "localhost"
tower_port = "1234"
tower_sk = PrivateKey()
tower_id = Cryptographer.get_compressed_pk(tower_sk.public_key)

mocked_return = None

# The height is never checked on the tests, so it can be hardcoded
CURRENT_HEIGHT = 1000


class TowerMock:
    def __init__(self, tower_sk):
        self.sk = tower_sk
        self.users = {}
        self.app = Flask(__name__)

        # Adds all the routes to the functions listed above.
        routes = {
            "/register": (self.register, ["POST"]),
            "/add_appointment": (self.add_appointment, ["POST"]),
            "/get_appointment": (self.get_appointment, ["POST"]),
        }

        for url, params in routes.items():
            self.app.add_url_rule(url, view_func=params[0], methods=params[1])

        # Setting Flask log to ERROR only so it does not mess with our logging. Also disabling flask initial messages
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        os.environ["WERKZEUG_RUN_MAIN"] = "true"

    def register(self):
        user_id = request.get_json().get("public_key")

        available_slots = 100 if user_id not in self.users else self.users[user_id]["available_slots"] + 100
        subscription_expiry = CURRENT_HEIGHT + 4320
        self.users[user_id] = {"available_slots": available_slots, "subscription_expiry": subscription_expiry}
        registration_receipt = receipts.create_registration_receipt(user_id, available_slots, subscription_expiry)

        rcode = constants.HTTP_OK
        response = {
            "public_key": user_id,
            "available_slots": self.users[user_id].get("available_slots"),
            "subscription_expiry": self.users[user_id].get("subscription_expiry"),
            "signature": Cryptographer.sign(registration_receipt, self.sk),
        }

        return response, rcode

    def add_appointment(self):
        appointment = Appointment.from_dict(request.get_json().get("appointment"))
        signature = request.get_json().get("signature")
        user_id = Cryptographer.get_compressed_pk(Cryptographer.recover_pk(appointment.serialize(), signature))

        if mocked_return == "success":
            response, rtype = add_appointment_success(appointment, signature, self.users[user_id], self.sk)
        elif mocked_return == "reject_no_slots":
            response, rtype = add_appointment_reject_no_slots()
        elif mocked_return == "reject_invalid":
            response, rtype = add_appointment_reject_invalid()
        elif mocked_return == "misbehaving_tower":
            response, rtype = add_appointment_misbehaving_tower(appointment, signature, self.users[user_id], self.sk)
        else:
            response, rtype = add_appointment_service_unavailable()

        return jsonify(response), rtype

    def get_appointment(self):
        locator = request.get_json().get("locator")
        message = f"get appointment {locator}"
        user_id = Cryptographer.get_compressed_pk(
            Cryptographer.recover_pk(message.encode(), request.get_json().get("signature"))
        )

        if (
            user_id in self.users
            and "appointments" in self.users[user_id]
            and locator in self.users[user_id]["appointments"]
        ):
            rcode = constants.HTTP_OK
            response = self.users[user_id]["appointments"][locator]
            response["status"] = "being_watched"

        else:
            rcode = constants.HTTP_NOT_FOUND
            response = {"locator": locator, "status": "not_found"}

        return jsonify(response), rcode


def add_appointment_success(appointment, signature, user, tower_sk):
    rcode = constants.HTTP_OK
    response = {
        "locator": appointment.locator,
        "signature": Cryptographer.sign(receipts.create_appointment_receipt(signature, CURRENT_HEIGHT), tower_sk),
        "start_block": CURRENT_HEIGHT,
        "available_slots": user.get("available_slots") - 1,
        "subscription_expiry": user.get("subscription_expiry"),
    }

    user["available_slots"] = response.get("available_slots")
    if user.get("appointments"):
        user["appointments"][appointment.locator] = appointment.to_dict()
    else:
        user["appointments"] = {appointment.locator: appointment.to_dict()}

    return response, rcode


def add_appointment_reject_no_slots():
    # This covers non-registered users and users with no available slots

    rcode = constants.HTTP_BAD_REQUEST
    response = {
        "error": "appointment rejected. Invalid signature or user does not have enough slots available",
        "error_code": errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS,
    }

    return response, rcode


def add_appointment_reject_invalid():
    # This covers malformed appointments (e.g. no json) and appointments with invalid data
    # Pick whatever reason, should not matter

    rcode = constants.HTTP_BAD_REQUEST
    response = {"error": "appointment rejected", "error_code": errors.APPOINTMENT_EMPTY_FIELD}

    return response, rcode


def add_appointment_service_unavailable():
    # This covers any reason why the service may be unavailable (e.g. tower run out of free slots)

    rcode = constants.HTTP_SERVICE_UNAVAILABLE
    response = {"error": "appointment rejected"}

    return response, rcode


def add_appointment_misbehaving_tower(appointment, signature, user, tower_sk):
    # This covers a tower signing with invalid keys
    wrong_sk = PrivateKey.from_hex(get_random_value_hex(32))
    wrong_sig = Cryptographer.sign(receipts.create_appointment_receipt(signature, CURRENT_HEIGHT), wrong_sk)

    response, rcode = add_appointment_success(appointment, signature, user, tower_sk)
    user["appointments"][appointment.locator]["signature"] = wrong_sig
    response["signature"] = wrong_sig

    return response, rcode


def get_random_value_hex(nbytes):
    pseudo_random_value = random.getrandbits(8 * nbytes)
    prv_hex = "{:x}".format(pseudo_random_value)
    return prv_hex.zfill(2 * nbytes)


@pytest.fixture(scope="session", autouse=True)
def init_tower():
    os.environ["TOWERS_DATA_DIR"] = "/tmp/watchtower"
    config = configparser.ConfigParser()
    config["general"] = {"max_retries": "5"}

    os.makedirs(os.environ["TOWERS_DATA_DIR"], exist_ok=True)

    with open(os.path.join(os.environ["TOWERS_DATA_DIR"], "watchtower.conf"), "w") as configfile:
        config.write(configfile)

    yield

    shutil.rmtree(os.environ["TOWERS_DATA_DIR"])


@pytest.fixture(scope="session", autouse=True)
def prng_seed():
    random.seed(0)


@pytest.fixture(scope="session", autouse=True)
def run_tower():
    tower = TowerMock(tower_sk)
    Thread(target=tower.app.run, kwargs={"host": tower_netaddr, "port": tower_port}, daemon=True).start()


def test_helpme_starts(node_factory):
    l1 = node_factory.get_node()
    # Test dynamically
    l1.rpc.plugin_start(plugin_path)
    l1.rpc.plugin_stop(plugin_path)
    l1.rpc.plugin_start(plugin_path)
    l1.stop()
    # Then statically
    l1.daemon.opts["plugin"] = plugin_path
    l1.start()


def test_watchtower(node_factory):
    """ Tests sending data to a single tower with short connection issue"""

    global mocked_return
    # FIXME: node_factory is a function scope fixture, so I cannot reuse it while splitting the tests logically
    l1, l2 = node_factory.line_graph(2, opts=[{"may_fail": True, "allow_broken_log": True}, {"plugin": plugin_path}])

    # Register a new tower
    l2.rpc.registertower("{}@{}:{}".format(tower_id, tower_netaddr, tower_port))

    # Make sure the tower in our list of towers
    tower_ids = [tower.get("id") for tower in l2.rpc.listtowers().get("towers")]
    assert tower_id in tower_ids

    # There are no appointments in the tower at the moment
    assert not l2.rpc.gettowerinfo(tower_id).get("appointments")

    # Force a new commitment
    mocked_return = "success"
    l1.rpc.pay(l2.rpc.invoice(25000000, "lbl1", "desc")["bolt11"])

    # Check that the tower got it (list is not empty anymore)
    # FIXME: it would be great to check the ids, I haven't found a way to check the list of commitments though.
    #        simply signing the last tx won't work since every payment creates two updates.
    appointments = l2.rpc.gettowerinfo(tower_id).get("appointments")
    assert appointments
    assert not l2.rpc.gettowerinfo(tower_id).get("pending_appointments")

    # Disconnect the tower and see how appointments get backed up
    mocked_return = "service_unavailable"
    l1.rpc.pay(l2.rpc.invoice(25000000, "lbl2", "desc")["bolt11"])
    pending_appointments = [
        data.get("appointment").get("locator") for data in l2.rpc.gettowerinfo(tower_id).get("pending_appointments")
    ]
    assert pending_appointments
    assert l2.rpc.gettowerinfo(tower_id).get("pending_appointments")

    # The fail has triggered the retry strategy. By "turning it back on" we should get the pending appointments trough
    mocked_return = "success"

    # Give it some time to switch
    while l2.rpc.gettowerinfo(tower_id).get("pending_appointments"):
        sleep(0.1)

    # The previously pending appointments are now part of the sent appointments
    assert set(pending_appointments).issubset(l2.rpc.gettowerinfo(tower_id).get("appointments").keys())


def test_watchtower_retry_offline(node_factory):
    """Tests sending data to a tower that gets offline for a while. Forces retry using ``retrytower``"""

    global mocked_return
    l1, l2 = node_factory.line_graph(2, opts=[{"may_fail": True, "allow_broken_log": True}, {"plugin": plugin_path}])

    # Send some appointments with to tower "offline"
    mocked_return = "service_unavailable"

    # There are no pending appointment atm
    assert not l2.rpc.gettowerinfo(tower_id).get("pending_appointments")

    l1.rpc.pay(l2.rpc.invoice(25000000, "lbl3", "desc")["bolt11"])
    pending_appointments = [
        data.get("appointment").get("locator") for data in l2.rpc.gettowerinfo(tower_id).get("pending_appointments")
    ]
    assert pending_appointments

    # Wait until the auto-retry gives up and force a retry manually
    while l2.rpc.gettowerinfo(tower_id).get("status") == "temporarily unreachable":
        sleep(0.1)
    l2.rpc.retrytower(tower_id)

    # After retrying with an offline tower the pending appointments are the exact same
    assert pending_appointments == [
        data.get("appointment").get("locator") for data in l2.rpc.gettowerinfo(tower_id).get("pending_appointments")
    ]

    # Now we can "turn the tower back on" and force a retry
    mocked_return = "success"
    l2.rpc.retrytower(tower_id)

    # Give it some time to send everything
    while l2.rpc.gettowerinfo(tower_id).get("pending_appointments"):
        sleep(0.1)

    # Check that all went trough
    assert set(pending_appointments).issubset(l2.rpc.gettowerinfo(tower_id).get("appointments").keys())


def test_watchtower_no_slots(node_factory):
    """Tests sending data to tower for a user that has no available slots"""

    global mocked_return
    l1, l2 = node_factory.line_graph(2, opts=[{"may_fail": True, "allow_broken_log": True}, {"plugin": plugin_path}])

    # Simulates there are no available slots when trying to send an appointment to the tower
    mocked_return = "reject_no_slots"

    # There are no pending appointments atm
    assert not l2.rpc.gettowerinfo(tower_id).get("pending_appointments")

    # Make a payment and the appointment should be left as pending
    l1.rpc.pay(l2.rpc.invoice(25000000, "lbl3", "desc")["bolt11"])
    pending_appointments = [
        data.get("appointment").get("locator") for data in l2.rpc.gettowerinfo(tower_id).get("pending_appointments")
    ]
    assert pending_appointments

    # Retrying should work but appointment won't go trough
    assert "Retrying tower" in l2.rpc.retrytower(tower_id)
    assert pending_appointments == [
        data.get("appointment").get("locator") for data in l2.rpc.gettowerinfo(tower_id).get("pending_appointments")
    ]

    # Adding slots + retrying should work
    mocked_return = "success"
    l2.rpc.retrytower(tower_id)
    while l2.rpc.gettowerinfo(tower_id).get("pending_appointments"):
        sleep(0.1)

    assert set(pending_appointments).issubset(l2.rpc.gettowerinfo(tower_id).get("appointments").keys())


def test_watchtower_invalid_appointment(node_factory):
    """Tests sending an invalid appointment to a tower"""

    global mocked_return
    l1, l2 = node_factory.line_graph(2, opts=[{"may_fail": True, "allow_broken_log": True}, {"plugin": plugin_path}])

    # Simulates sending an appointment with invalid data to the tower
    mocked_return = "reject_invalid"

    # There are no invalid appointment atm
    assert not l2.rpc.gettowerinfo(tower_id).get("invalid_appointments")

    # Make a payment and the appointment should be flagged as invalid
    l1.rpc.pay(l2.rpc.invoice(25000000, "lbl4", "desc")["bolt11"])

    # The appointments have been saved as invalid
    assert l2.rpc.gettowerinfo(tower_id).get("invalid_appointments")


def test_watchtower_multiple_towers(node_factory):
    """ Test sending data to multiple towers at the same time"""
    global mocked_return

    # Create the new tower
    another_tower_netaddr = "localhost"
    another_tower_port = "5678"
    another_tower_sk = PrivateKey()
    another_tower_id = Cryptographer.get_compressed_pk(another_tower_sk.public_key)

    another_tower = TowerMock(another_tower_sk)
    Thread(
        target=another_tower.app.run, kwargs={"host": another_tower_netaddr, "port": another_tower_port}, daemon=True
    ).start()

    l1, l2 = node_factory.line_graph(2, opts=[{"may_fail": True, "allow_broken_log": True}, {"plugin": plugin_path}])

    # Register a new tower
    l2.rpc.registertower("{}@{}:{}".format(another_tower_id, another_tower_netaddr, another_tower_port))

    # Make sure the tower in our list of towers
    tower_ids = [tower.get("id") for tower in l2.rpc.listtowers().get("towers")]
    assert another_tower_id in tower_ids

    # Force a new commitment
    mocked_return = "success"
    l1.rpc.pay(l2.rpc.invoice(25000000, "lbl6", "desc")["bolt11"])

    # Check that both towers got it
    another_tower_appointments = l2.rpc.gettowerinfo(another_tower_id).get("appointments")
    assert another_tower_appointments
    assert not l2.rpc.gettowerinfo(another_tower_id).get("pending_appointments")
    assert set(another_tower_appointments).issubset(l2.rpc.gettowerinfo(tower_id).get("appointments"))


def test_watchtower_misbehaving(node_factory):
    """Tests sending an appointment to a misbehaving tower"""

    global mocked_return
    l1, l2 = node_factory.line_graph(2, opts=[{"may_fail": True, "allow_broken_log": True}, {"plugin": plugin_path}])

    # Simulates a tower that replies with an invalid signature
    mocked_return = "misbehaving_tower"

    # There is no proof of misbehaviour atm
    assert not l2.rpc.gettowerinfo(tower_id).get("misbehaving_proof")

    # Make a payment and the appointment make it to the tower, but the response will contain an invalid signature
    l1.rpc.pay(l2.rpc.invoice(25000000, "lbl5", "desc")["bolt11"])

    # The tower should have stored the proof of misbehaviour
    tower_info = l2.rpc.gettowerinfo(tower_id)
    assert tower_info.get("status") == "misbehaving"
    assert tower_info.get("misbehaving_proof")


def test_get_appointment(node_factory):
    l1, l2 = node_factory.line_graph(2, opts=[{"may_fail": True, "allow_broken_log": True}, {"plugin": plugin_path}])

    local_appointments = l2.rpc.gettowerinfo(tower_id).get("appointments")
    # Get should get a reply for every local appointment
    for locator in local_appointments:
        response = l2.rpc.getappointment(tower_id, locator)
        assert response.get("locator") == locator
        assert response.get("status") == "being_watched"

    # Made up appointments should return a 404
    rand_locator = get_random_value_hex(16)
    response = l2.rpc.getappointment(tower_id, rand_locator)
    assert response.get("locator") == rand_locator
    assert response.get("status") == "not_found"
