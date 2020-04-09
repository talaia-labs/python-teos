#!/usr/bin/env python3
import os
import plyvel
from pyln.client import Plugin

from common.config_loader import ConfigLoader
from common.cryptographer import Cryptographer

import arg_parser
from tower_info import TowerInfo
from towers_dbm import TowersDBM
from keys import generate_keys, load_keys
from net.http import post_request, process_post_response
from exceptions import TowerConnectionError, TowerResponseError, InvalidParameter


DATA_DIR = os.path.expanduser("~/.teos_cli/")
CONF_FILE_NAME = "teos_cli.conf"

DEFAULT_CONF = {
    "DEFAULT_PORT": {"value": 9814, "type": int},
    "APPOINTMENTS_FOLDER_NAME": {"value": "appointment_receipts", "type": str, "path": True},
    "TOWERS_DB": {"value": "towers", "type": str, "path": True},
    "CLI_PRIVATE_KEY": {"value": "cli_sk.der", "type": str, "path": True},
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

    # FIXME: All responses from the tower should be signed. Not using teos_pk atm.

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
    commitment_txid = kwargs.get("commitment_txid")
    penalty_tx = kwargs.get("penalty_tx")
    plugin.log("commitment_txid {}, penalty_tx: {}".format(commitment_txid, penalty_tx))
    return {"result": "continue"}


@plugin.method("listtowers")
def list_towers(plugin):
    return {k: v.to_dict() for k, v in plugin.wt_client.towers.items()}


plugin.run()
