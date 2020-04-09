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
            self.towers[tower_id] = TowerInfo.from_dict(tower_info)


@plugin.init()
def init(options, configuration, plugin):
    try:
        plugin.log("Generating a new key pair for the watchtower client. Keys stored at {}".format(DATA_DIR))
        cli_sk, compressed_cli_pk = generate_keys(DATA_DIR)

    except FileExistsError:
        plugin.log("A key file for the watchtower client already exists. Loading it")
        cli_sk, compressed_cli_pk = load_keys(DATA_DIR)

    plugin.log("Plugin watchtower client initialized")
    config_loader = ConfigLoader(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF, {})

    try:
        plugin.wt_client = WTClient(cli_sk, compressed_cli_pk, config_loader.build_config())
    except plyvel.IOError:
        plugin.log("Cannot load towers db. Resource temporarily unavailable")
        # TODO: Check how to make the plugin stop


@plugin.method("register", desc="Register your public key with the tower")
def register(plugin, *args):
    """
    Registers the user to the tower.

    Args:
        plugin (:obj:`Plugin`): this plugin.
        args (:obj:`list`): a list of arguments. Must contain the tower_id and endpoint.

    Accepted input formats:
        - tower_id@host:port
        - tower_id@host (will default port to DEFAULT_PORT)
        - tower_id host port
        - tower_id host (will default port to DEFAULT_PORT)

    Returns:
        :obj:`dict`: a dictionary containing the subscription data.
    """

    try:
        tower_id, tower_endpoint = arg_parser.parse_register_arguments(
            args, plugin.wt_client.config.get("DEFAULT_PORT")
        )

        # Defaulting to http hosts for now
        if not tower_endpoint.startswith("http"):
            tower_endpoint = "http://" + tower_endpoint

        # Send request to the server.
        register_endpoint = "{}/register".format(tower_endpoint)
        data = {"public_key": plugin.wt_client.user_id}

        plugin.log("Registering in the Eye of Satoshi")

        response = process_post_response(post_request(data, register_endpoint))
        plugin.log("Registration succeeded. Available slots: {}".format(response.get("available_slots")))

        # Save data
        tower_info = TowerInfo(tower_endpoint, response.get("available_slots"))
        plugin.wt_client.towers[tower_id] = tower_info
        plugin.wt_client.db_manager.store_tower_record(tower_id, tower_info)

        return response

    except (InvalidParameter, TowerConnectionError, TowerResponseError) as e:
        plugin.log(str(e), level="error")
        return e.to_json()


@plugin.method("getappointment", desc="Gets appointment data from the tower given a locator")
def get_appointment(plugin, *args):
    """
    Gets information about an appointment from the tower.

    Args:
        plugin (:obj:`Plugin`): this plugin.
        args (:obj:`list`): a list of arguments. Must contain a single argument, the locator.

    Returns:
        :obj:`dict`: a dictionary containing the appointment data.
    """

    # FIXME: All responses from the tower should be signed.

    try:
        tower_id, locator = arg_parser.parse_get_appointment_arguments(args)

        if tower_id not in plugin.wt_client.towers:
            raise InvalidParameter("tower_id is not within the registered towers", tower_id=tower_id)

        message = "get appointment {}".format(locator)
        signature = Cryptographer.sign(message.encode(), plugin.wt_client.sk)
        data = {"locator": locator, "signature": signature}

        # Send request to the server.
        get_appointment_endpoint = "{}/get_appointment".format(plugin.wt_client.towers[tower_id].endpoint)
        plugin.log("Requesting appointment from the Eye of Satoshi at {}".format(get_appointment_endpoint))

        response = process_post_response(post_request(data, get_appointment_endpoint))
        return response

    except (InvalidParameter, TowerConnectionError, TowerResponseError) as e:
        plugin.log(str(e), level="error")
        return e.to_json()


@plugin.hook("commitment_revocation")
def add_appointment(plugin, **kwargs):
    try:
        # FIXME: start_time and end_time are temporary. Fix it on the tower side and remove it from there
        block_height = plugin.rpc.getchaininfo().get("blockcount")
        start_time = block_height + 1
        end_time = block_height + 10

        commitment_txid, penalty_tx = arg_parser.parse_add_appointment_arguments(kwargs)
        appointment = Appointment(
            locator=compute_locator(commitment_txid),
            start_time=start_time,
            end_time=end_time,
            to_self_delay=20,
            encrypted_blob=Cryptographer.encrypt(penalty_tx, commitment_txid),
        )

        signature = Cryptographer.sign(appointment.serialize(), plugin.wt_client.sk)
        data = {"appointment": appointment.to_dict(), "signature": signature}

        # Send appointment to the server.
        # FIXME: sending the appointment to all registered towers atm. Some management would be nice.
        for tower_id, tower in plugin.wt_client.towers.items():
            plugin.log("Sending appointment to the Eye of Satoshi at {}".format(tower.endpoint))
            add_appointment_endpoint = "{}/add_appointment".format(tower.endpoint)
            response = process_post_response(post_request(data, add_appointment_endpoint))

            signature = response.get("signature")
            # Check that the server signed the appointment as it should.
            if not signature:
                raise TowerResponseError("The response does not contain the signature of the appointment")

            rpk = Cryptographer.recover_pk(appointment.serialize(), signature)
            if not tower_id != Cryptographer.get_compressed_pk(rpk):
                raise TowerResponseError("The returned appointment's signature is invalid")

            plugin.log("Appointment accepted and signed by the Eye of Satoshi at {}".format(tower.endpoint))
            plugin.log("Remaining slots: {}".format(response.get("available_slots")))

            # TODO: Not storing the whole appointments for now. The node should be able to recreate all the required
            #       data if needed.
            plugin.wt_client.towers[tower_id].appointments[appointment.locator] = signature
            plugin.wt_client.db_manager.store_tower_record(tower_id, plugin.wt_client.towers[tower_id])

    except (InvalidParameter, EncryptionError, SignatureError, TowerResponseError) as e:
        plugin.log(str(e), level="error")

    return {"result": "continue"}


@plugin.method("listtowers")
def list_towers(plugin):
    return {k: v.to_dict() for k, v in plugin.wt_client.towers.items()}


plugin.run()
