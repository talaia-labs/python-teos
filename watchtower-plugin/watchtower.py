#!/usr/bin/env python3
import os
import plyvel
from pyln.client import Plugin

from common.tools import compute_locator
from common.appointment import Appointment
from common.config_loader import ConfigLoader
from common.cryptographer import Cryptographer
from common.exceptions import InvalidParameter, SignatureError, EncryptionError

import arg_parser
from tower_info import TowerInfo
from towers_dbm import TowersDBM
from keys import generate_keys, load_keys
from net.http import post_request, process_post_response
from exceptions import TowerConnectionError, TowerResponseError


DATA_DIR = os.path.expanduser("~/.watchtower/")
CONF_FILE_NAME = "watchtower.conf"

DEFAULT_CONF = {
    "DEFAULT_PORT": {"value": 9814, "type": int},
    "APPOINTMENTS_FOLDER_NAME": {"value": "appointment_receipts", "type": str, "path": True},
    "TOWERS_DB": {"value": "towers", "type": str, "path": True},
    "PRIVATE_KEY": {"value": "sk.der", "type": str, "path": True},
}


plugin = Plugin()


class WTClient:
    def __init__(self, sk, user_id, config):
        self.sk = sk
        self.user_id = user_id
        self.db_manager = TowersDBM(config.get("TOWERS_DB"), plugin)
        self.towers = {}
        self.config = config

        # Populate the towers dict with data from the db
        for tower_id, tower_info in self.db_manager.load_all_tower_records().items():
            self.towers[tower_id] = TowerInfo.from_dict(tower_info).get_summary()


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

        plugin.log("Registering in the Eye of Satoshi")

        response = process_post_response(post_request(data, register_endpoint))
        plugin.log("Registration succeeded. Available slots: {}".format(response.get("available_slots")))

        # Save data
        tower_info = TowerInfo(tower_netaddr, response.get("available_slots"))
        plugin.wt_client.towers[tower_id] = tower_info.get_summary()
        plugin.wt_client.db_manager.store_tower_record(tower_id, tower_info)

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
        plugin.log("Requesting appointment from the Eye of Satoshi at {}".format(get_appointment_endpoint))

        response = process_post_response(post_request(data, get_appointment_endpoint))
        return response

    except (InvalidParameter, TowerConnectionError, TowerResponseError) as e:
        plugin.log(str(e), level="warn")
        return e.to_json()


@plugin.method("listtowers", desc="List all towers registered towers.")
def list_towers(plugin):
    towers_info = {"towers": []}
    for k, v in plugin.wt_client.towers.items():
        towers_info["towers"].append({"id": k, **v})

    return towers_info


@plugin.hook("commitment_revocation")
def add_appointment(plugin, **kwargs):
    try:
        commitment_txid, penalty_tx = arg_parser.parse_add_appointment_arguments(kwargs)
        appointment = Appointment(
            locator=compute_locator(commitment_txid),
            to_self_delay=20,  # does not matter for now, any value 20-2^32-1 would do
            encrypted_blob=Cryptographer.encrypt(penalty_tx, commitment_txid),
        )

        signature = Cryptographer.sign(appointment.serialize(), plugin.wt_client.sk)
        data = {"appointment": appointment.to_dict(), "signature": signature}

        # Send appointment to the server.
        # FIXME: sending the appointment to all registered towers atm. Some management would be nice.
        for tower_id, tower in plugin.wt_client.towers.items():
            try:
                plugin.log("Sending appointment to the Eye of Satoshi at {}".format(tower.get("netaddr")))
                add_appointment_endpoint = "{}/add_appointment".format(tower.get("netaddr"))
                response = process_post_response(post_request(data, add_appointment_endpoint))

                signature = response.get("signature")
                # Check that the server signed the appointment as it should.
                if not signature:
                    raise TowerResponseError("The response does not contain the signature of the appointment")

                rpk = Cryptographer.recover_pk(appointment.serialize(), signature)
                if not tower_id != Cryptographer.get_compressed_pk(rpk):
                    raise TowerResponseError("The returned appointment's signature is invalid")

                plugin.log("Appointment accepted and signed by the Eye of Satoshi at {}".format(tower.get("netaddr")))
                plugin.log("Remaining slots: {}".format(response.get("available_slots")))

                # TODO: Not storing the whole appointments for now. The node can recreate all the data if needed.
                # DISCUSS: It may be worth checking that the available slots match instead of blindly trusting.

                # Update  TowersDB
                tower_info = TowerInfo.from_dict(plugin.wt_client.db_manager.load_tower_record(tower_id))
                tower_info.appointments[appointment.locator] = signature
                tower_info.available_slots = response.get("available_slots")
                plugin.wt_client.db_manager.store_tower_record(tower_id, tower_info)

                # Update memory
                plugin.wt_client.towers[tower_id]["available_slots"] = response.get("available_slots")

            except TowerConnectionError as e:
                # TODO: Implement retry logic
                plugin.log(str(e))

            except TowerResponseError as e:
                plugin.log(str(e))

    except (InvalidParameter, EncryptionError, SignatureError, TowerResponseError) as e:
        plugin.log(str(e), level="warn")

    return {"result": "continue"}


plugin.run()
