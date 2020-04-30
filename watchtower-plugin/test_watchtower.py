import random
from time import sleep
from coincurve import PrivateKey
from threading import Thread
from flask import Flask, request, jsonify
from pyln.testing.fixtures import *  # noqa: F401,F403

from common import errors
from common import constants
from common.appointment import Appointment
from common.cryptographer import Cryptographer

plugin_path = os.path.join(os.path.dirname(__file__), "watchtower.py")
tower_netaddr = "localhost"
tower_port = "1234"
tower_sk = PrivateKey()
tower_id = Cryptographer.get_compressed_pk(tower_sk.public_key)

mocked_return = None


def add_appointment_success(appointment, available_slots, subscription_expiry):
    rcode = constants.HTTP_OK
    response = {
        "locator": appointment.locator,
        "signature": Cryptographer.sign(appointment.serialize(), tower_sk),
        "available_slots": available_slots - 1,
        "subscription_expiry": subscription_expiry,
    }
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


@pytest.fixture(scope="session", autouse=True)
def prng_seed():
    random.seed(0)


def get_random_value_hex(nbytes):
    pseudo_random_value = random.getrandbits(8 * nbytes)
    prv_hex = "{:x}".format(pseudo_random_value)
    return prv_hex.zfill(2 * nbytes)


@pytest.fixture(scope="session")
def tower_mock():
    app = Flask(__name__)

    users = {}

    @app.route("/register", methods=["POST"])
    def register():

        user_id = request.get_json().get("public_key")

        if user_id not in users:
            users[user_id] = {"available_slots": 100, "subscription_expiry": 4320}
        else:
            users[user_id]["available_slots"] = 100
            users[user_id]["subscription_expiry"] = 4320

        rcode = constants.HTTP_OK
        response = {"public_key": user_id, **users[user_id]}

        return response, rcode

    @app.route("/add_appointment", methods=["POST"])
    def add_appointment():

        if mocked_return == "success":
            appointment = Appointment.from_dict(request.get_json().get("appointment"))
            user_id = Cryptographer.get_compressed_pk(
                Cryptographer.recover_pk(appointment.serialize(), request.get_json().get("signature"))
            )
            data, rtype = add_appointment_success(appointment, **users[user_id])
        elif mocked_return == "reject_no_slots":
            data, rtype = add_appointment_reject_no_slots()
        elif mocked_return == "reject_invalid":
            data, rtype = add_appointment_reject_invalid()
        else:
            data, rtype = add_appointment_service_unavailable()

        return jsonify(data), rtype

    @app.route("/get_appointment", methods=["POST"])
    def get_appointment():
        pass

    # Setting Flask log to ERROR only so it does not mess with our logging. Also disabling flask initial messages
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    os.environ["WERKZEUG_RUN_MAIN"] = "true"

    yield app


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


def test_watchtower(node_factory, tower_mock):
    global mocked_return

    l1, l2 = node_factory.line_graph(2, opts=[{"may_fail": True, "allow_broken_log": True}, {"plugin": plugin_path}])

    # Start the tower mock in a different process
    Thread(target=tower_mock.run, kwargs={"host": tower_netaddr, "port": tower_port}, daemon=True).start()

    # Register a new tower
    l2.rpc.registertower("{}@{}:{}".format(tower_id, tower_netaddr, tower_port))

    # Make sure we the tower in our list of towers
    tower_ids = [tower.get("id") for tower in l2.rpc.listtowers().get("towers")]
    assert tower_id in tower_ids

    # There are no appointments in the tower at the moment
    assert not l2.rpc.gettowerinfo(tower_id).get("appointments")

    # Force a new commitment
    mocked_return = "success"
    l1.rpc.pay(l2.rpc.invoice(25000000, "lbl1", "desc1")["bolt11"])

    # Check that the tower got it (list is not empty anymore)
    # FIXME: it would be great to check the ids, need to run as dev tho and its currently failing to compile
    appointments = l2.rpc.gettowerinfo(tower_id).get("appointments")
    assert appointments

    # Disconnect the tower and see how appointments get backed up
    assert not l2.rpc.gettowerinfo(tower_id).get("pending_appointments")

    mocked_return = "service_unavailable"
    l1.rpc.pay(l2.rpc.invoice(25000000, "lbl2", "desc1")["bolt11"])
    pending_appointments = [
        data.get("appointment").get("locator") for data in l2.rpc.gettowerinfo(tower_id).get("pending_appointments")
    ]
    assert pending_appointments

    # The fail has triggered the retry strategy. By "turning it back on" we should get the pending appointments trough
    mocked_return = "success"
    sleep(1)
    assert not l2.rpc.gettowerinfo(tower_id).get("pending_appointments")
    assert set(pending_appointments).issubset(l2.rpc.gettowerinfo(tower_id).get("appointments").keys())

    # TODO: reduce max retries and force retry with retrytower


# TODO: Check rejections
