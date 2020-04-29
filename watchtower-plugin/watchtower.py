#!/usr/bin/env python3
import os
import plyvel
from queue import Queue
from pyln.client import Plugin
from threading import Thread, Lock

from common.tools import compute_locator
from common.appointment import Appointment
from common.config_loader import ConfigLoader
from common.cryptographer import Cryptographer
from common.exceptions import InvalidParameter, SignatureError, EncryptionError

import arg_parser
from retrier import Retrier
from tower_info import TowerInfo
from towers_dbm import TowersDBM
from keys import generate_keys, load_keys
from exceptions import TowerConnectionError, TowerResponseError
from net.http import post_request, process_post_response, add_appointment


DATA_DIR = os.path.expanduser("~/.watchtower/")
CONF_FILE_NAME = "watchtower.conf"

DEFAULT_CONF = {
    "DEFAULT_PORT": {"value": 9814, "type": int},
    "MAX_RETRIES": {"value": 30, "type": int},
    "APPOINTMENTS_FOLDER_NAME": {"value": "appointment_receipts", "type": str, "path": True},
    "TOWERS_DB": {"value": "towers", "type": str, "path": True},
    "PRIVATE_KEY": {"value": "sk.der", "type": str, "path": True},
}


plugin = Plugin()


class WTClient:
    def __init__(self, sk, user_id, config):
        self.sk = sk
        self.user_id = user_id
        self.towers = {}
        self.tmp_unreachable_towers = []
        self.db_manager = TowersDBM(config.get("TOWERS_DB"), plugin)
        self.retrier = Retrier(config.get("MAX_RETRIES"), Queue())
        self.config = config
        self.lock = Lock()

        # Populate the towers dict with data from the db
        for tower_id, tower_info in self.db_manager.load_all_tower_records().items():
            self.towers[tower_id] = TowerInfo.from_dict(tower_info).get_summary()

        Thread(target=self.retrier.manage_retry, args=[plugin], daemon=True).start()

    def update_tower_state(self, tower_id, tower_info):
        self.lock.acquire()
        self.towers[tower_id] = tower_info.get_summary()
        self.db_manager.store_tower_record(tower_id, tower_info)
        self.lock.release()


@plugin.init()
def init(options, configuration, plugin):
    try:
        user_sk, user_id = generate_keys(DATA_DIR)
        plugin.log("Generating a new key pair for the watchtower client. Keys stored at {}".format(DATA_DIR))

    except FileExistsError:
        plugin.log("A key file for the watchtower client already exists. Loading it")
        user_sk, user_id = load_keys(DATA_DIR)

    plugin.log("Plugin watchtower client initialized. User id = {}".format(user_id))
    config_loader = ConfigLoader(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF, {})

    try:
        plugin.wt_client = WTClient(user_sk, user_id, config_loader.build_config())
    except plyvel.IOError:
        error = "Cannot load towers db. Resource temporarily unavailable"
        plugin.log("Cannot load towers db. Resource temporarily unavailable")
        raise IOError(error)


@plugin.method("registertower", desc="Register your public key (user id) with the tower.")
def register(plugin, tower_id, host=None, port=None):
    """
    Registers the user to the tower.

    Args:
        plugin (:obj:`Plugin`): this plugin.
        tower_id (:obj:`str`): the identifier of the tower to connect to (a compressed public key).
        host (:obj:`str`): the ip or hostname to connect to, optional.
        host (:obj:`int`): the port to connect to, optional.

    Accepted tower_id formats:
        - tower_id@host:port
        - tower_id host port
        - tower_id@host (will default port to DEFAULT_PORT)
        - tower_id host (will default port to DEFAULT_PORT)

    Returns:
        :obj:`dict`: a dictionary containing the subscription data.
    """

    try:
        tower_id, tower_netaddr = arg_parser.parse_register_arguments(tower_id, host, port, plugin.wt_client.config)

        # Defaulting to http hosts for now
        if not tower_netaddr.startswith("http"):
            tower_netaddr = "http://" + tower_netaddr

        # Send request to the server.
        register_endpoint = "{}/register".format(tower_netaddr)
        data = {"public_key": plugin.wt_client.user_id}

        plugin.log("Registering in the Eye of Satoshi (tower_id={})".format(tower_id))

        response = process_post_response(post_request(data, register_endpoint, tower_id))
        plugin.log("Registration succeeded. Available slots: {}".format(response.get("available_slots")))

        # Save data
        tower_info = TowerInfo(tower_netaddr, response.get("available_slots"))
        plugin.wt_client.update_tower_state(tower_id, tower_info)

        return response

    except (InvalidParameter, TowerConnectionError, TowerResponseError) as e:
        plugin.log(str(e), level="warn")
        return e.to_json()


@plugin.method("getappointment", desc="Gets appointment data from the tower given the tower id and the locator.")
def get_appointment(plugin, tower_id, locator):
    """
    Gets information about an appointment from the tower.

    Args:
        plugin (:obj:`Plugin`): this plugin.
        tower_id (:obj:`str`): the identifier of the tower to query.
        locator (:obj:`str`): the appointment locator.

    Returns:
        :obj:`dict`: a dictionary containing the appointment data.
    """

    # FIXME: All responses from the tower should be signed.

    try:
        tower_id, locator = arg_parser.parse_get_appointment_arguments(tower_id, locator)

        if tower_id not in plugin.wt_client.towers:
            raise InvalidParameter("tower_id is not within the registered towers", tower_id=tower_id)

        message = "get appointment {}".format(locator)
        signature = Cryptographer.sign(message.encode(), plugin.wt_client.sk)
        data = {"locator": locator, "signature": signature}

        # Send request to the server.
        get_appointment_endpoint = "{}/get_appointment".format(plugin.wt_client.towers[tower_id].get("netaddr"))
        plugin.log("Requesting appointment from {}".format(tower_id))

        response = process_post_response(post_request(data, get_appointment_endpoint, tower_id))
        return response

    except (InvalidParameter, TowerConnectionError, TowerResponseError) as e:
        plugin.log(str(e), level="warn")
        return e.to_json()


@plugin.method("listtowers", desc="List all towers registered towers.")
def list_towers(plugin):
    towers_info = {"towers": []}
    for tower_id, info in plugin.wt_client.towers.items():
        values = {k: v for k, v in info.items() if k != "pending_appointments"}
        pending_appointments = [appointment.get("locator") for appointment, signature in info["pending_appointments"]]
        invalid_appointments = [appointment.get("locator") for appointment, signature in info["invalid_appointments"]]
        values["pending_appointments"] = pending_appointments
        values["invalid_appointments"] = invalid_appointments
        towers_info["towers"].append({"id": tower_id, **values})

    return towers_info


@plugin.method("gettowerinfo", desc="List all towers registered towers.")
def get_tower_info(plugin, tower_id):
    tower_info = TowerInfo.from_dict(plugin.wt_client.db_manager.load_tower_record(tower_id))
    pending_appointments = [
        {"appointment": appointment, "signature": signature}
        for appointment, signature in tower_info.pending_appointments
    ]
    invalid_appointments = [
        {"appointment": appointment, "tower_signature": signature}
        for appointment, signature in tower_info.invalid_appointments
    ]
    tower_info.pending_appointments = pending_appointments
    tower_info.invalid_appointments = invalid_appointments
    return {"id": tower_id, **tower_info.to_dict()}


@plugin.method("retrytower", desc="Retry to send pending appointment to an unreachable tower.")
def retry_tower(plugin, tower_id):
    tower_info = TowerInfo.from_dict(plugin.wt_client.db_manager.load_tower_record(tower_id))

    if not tower_info:
        return {"error": "{} is not a registered tower".format(tower_id)}
    if tower_info.status != "unreachable":
        return {"error": "{} is not unreachable".format(tower_id)}
    if not tower_info.pending_appointments:
        return {"error": "{} does not have pending appointments".format(tower_id)}

    message = "Retrying tower {}".format(tower_id)
    plugin.log(message)
    plugin.wt_client.retrier.temp_unreachable_towers.put(tower_id)

    return message


@plugin.hook("commitment_revocation")
def on_commitment_revocation(plugin, **kwargs):
    try:
        commitment_txid, penalty_tx = arg_parser.parse_add_appointment_arguments(kwargs)
        appointment = Appointment(
            locator=compute_locator(commitment_txid),
            to_self_delay=20,  # does not matter for now, any value 20-2^32-1 would do
            encrypted_blob=Cryptographer.encrypt(penalty_tx, commitment_txid),
        )
        signature = Cryptographer.sign(appointment.serialize(), plugin.wt_client.sk)

        # Send appointment to the towers.
        # FIXME: sending the appointment to all registered towers atm. Some management would be nice.
        for tower_id, tower in plugin.wt_client.towers.items():
            tower_info = TowerInfo.from_dict(plugin.wt_client.db_manager.load_tower_record(tower_id))

            if tower_info.status == "reachable":
                status = add_appointment(plugin, tower_id, tower_info, appointment.to_dict(), signature)
                if status == "temporarily unreachable":
                    tower_info.pending_appointments.append((appointment.to_dict(), signature))
                    plugin.wt_client.retrier.temp_unreachable_towers.put(tower_id)

            elif tower_info.status != "misbehaving":
                if tower_info.status in ["temporarily unreachable", "unreachable"]:
                    plugin.log("{} is {}. Adding appointment to pending".format(tower_id, tower_info.status))
                elif tower_info == "subscription error":
                    plugin.log("There is a subscription issue with {}. Adding appointment to pending".format(tower_id))

                tower_info.pending_appointments.append((appointment.to_dict(), signature))

            # Update memory and TowersDB
            plugin.wt_client.update_tower_state(tower_id, tower_info)

    except (InvalidParameter, EncryptionError, SignatureError) as e:
        plugin.log(str(e), level="warn")

    except TowerConnectionError:
        pass

    return {"result": "continue"}


plugin.run()
