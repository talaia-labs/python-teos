#!/usr/bin/env python3
import os
import plyvel
from queue import Queue
from pyln.client import Plugin
from threading import Thread, Lock

import common.receipts as receipts
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


DATA_DIR = os.getenv("TOWERS_DATA_DIR", os.path.expanduser("~/.watchtower/"))
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
    """
    Holds all the data regarding the watchtower client.

    Fires an additional tread to take care of retries.

    Args:
        sk (:obj:`PrivateKey): the user private key. Used to sign appointment sent to the towers.
        user_id (:obj:`PrivateKey): the identifier of the user (compressed public key).
        config (:obj:`dict`): the client configuration loaded on a dictionary.

    Attributes:
        towers (:obj:`dict`): a collection of registered towers. Indexed by tower_id, populated with :obj:`TowerSummary`
            objects.
        db_manager (:obj:`towers_dbm.TowersDBM`): a manager to interact with the towers database.
        retrier (:obj:`retrier.Retrier`): a ``Retrier`` in charge of retrying sending jobs to temporarily unreachable
            towers.
        lock (:obj:`Lock`): a thread lock.
    """

    def __init__(self, sk, user_id, config):
        self.sk = sk
        self.user_id = user_id
        self.towers = {}
        self.db_manager = TowersDBM(config.get("TOWERS_DB"), plugin)
        self.retrier = Retrier(config.get("MAX_RETRIES"), Queue())
        self.config = config
        self.lock = Lock()

        # Populate the towers dict with data from the db
        for tower_id, tower_info in self.db_manager.load_all_tower_records().items():
            self.towers[tower_id] = TowerInfo.from_dict(tower_info).get_summary()

        Thread(target=self.retrier.manage_retry, args=[plugin], daemon=True).start()

    def update_tower_state(self, tower_id, tower_update):
        """
        Updates the state of a tower both in memory and disk.

        Access if restricted thought a lock to prevent race conditions.

        Args:
            tower_id (:obj:`str`): the identifier of the tower to be updated.
            tower_update (:obj:`dict`): a dictionary containing the data to be added / removed.
        """

        self.lock.acquire()
        tower_info = TowerInfo.from_dict(self.db_manager.load_tower_record(tower_id))

        if "status" in tower_update:
            tower_info.status = tower_update.get("status")
        if "appointment" in tower_update:
            locator, signature = tower_update.get("appointment")
            tower_info.appointments[locator] = signature
            tower_info.available_slots = tower_update.get("available_slots")
        if "pending_appointment" in tower_update:
            data, action = tower_update.get("pending_appointment")
            if action == "add":
                tower_info.pending_appointments.append(list(data))
            else:
                tower_info.pending_appointments.remove(list(data))
        if "invalid_appointment" in tower_update:
            tower_info.invalid_appointments.append(list(tower_update.get("invalid_appointment")))

        if "misbehaving_proof" in tower_update:
            tower_info.misbehaving_proof = tower_update.get("misbehaving_proof")

        self.towers[tower_id] = tower_info.get_summary()
        self.db_manager.store_tower_record(tower_id, tower_info)
        self.lock.release()


@plugin.init()
def init(options, configuration, plugin):
    """Initializes the plugin"""

    try:
        user_sk, user_id = generate_keys(DATA_DIR)
        plugin.log(f"Generating a new key pair for the watchtower client. Keys stored at {DATA_DIR}")

    except FileExistsError:
        plugin.log("A key file for the watchtower client already exists. Loading it")
        user_sk, user_id = load_keys(DATA_DIR)

    plugin.log(f"Plugin watchtower client initialized. User id = {user_id}")
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
        port (:obj:`int`): the port to connect to, optional.

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
        register_endpoint = f"{tower_netaddr}/register"
        data = {"public_key": plugin.wt_client.user_id}

        plugin.log(f"Registering in the Eye of Satoshi (tower_id={tower_id})")

        response = process_post_response(post_request(data, register_endpoint, tower_id))
        available_slots = response.get("available_slots")
        subscription_expiry = response.get("subscription_expiry")
        tower_signature = response.get("signature")

        if available_slots is None or not isinstance(available_slots, int):
            raise TowerResponseError(f"available_slots is missing or of wrong type ({available_slots})")
        if subscription_expiry is None or not isinstance(subscription_expiry, int):
            raise TowerResponseError(f"subscription_expiry is missing or of wrong type ({subscription_expiry})")
        if tower_signature is None or not isinstance(tower_signature, str):
            raise TowerResponseError(f"signature is missing or of wrong type ({tower_signature})")

        # Check tower signature
        registration_receipt = receipts.create_registration_receipt(
            plugin.wt_client.user_id, available_slots, subscription_expiry
        )
        Cryptographer.recover_pk(registration_receipt, tower_signature)

        plugin.log(f"Registration succeeded. Available slots: {available_slots}")

        # Save data
        tower_info = TowerInfo(tower_netaddr, available_slots)
        plugin.wt_client.lock.acquire()
        plugin.wt_client.towers[tower_id] = tower_info.get_summary()
        plugin.wt_client.db_manager.store_tower_record(tower_id, tower_info)
        plugin.wt_client.lock.release()

        return response

    except (InvalidParameter, TowerConnectionError, TowerResponseError, SignatureError) as e:
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

        message = f"get appointment {locator}"
        signature = Cryptographer.sign(message.encode(), plugin.wt_client.sk)
        data = {"locator": locator, "signature": signature}

        # Send request to the server.
        tower_netaddr = plugin.wt_client.towers[tower_id].netaddr
        get_appointment_endpoint = f"{tower_netaddr}/get_appointment"
        plugin.log(f"Requesting appointment from {tower_id}")

        response = process_post_response(post_request(data, get_appointment_endpoint, tower_id))
        return response

    except (InvalidParameter, TowerConnectionError, TowerResponseError) as e:
        plugin.log(str(e), level="warn")
        return e.to_json()


@plugin.method("listtowers", desc="List all registered towers.")
def list_towers(plugin):
    """
    Lists all the registered towers. The given information comes from memory, so it is summarized.

    Args:
        plugin (:obj:`Plugin`): this plugin.

    Returns:
        :obj:`dict`: a dictionary containing the registered towers data.
    """

    towers_info = {"towers": []}
    for tower_id, tower in plugin.wt_client.towers.items():
        values = {k: v for k, v in tower.to_dict().items() if k not in ["pending_appointments", "invalid_appointments"]}
        pending_appointments = [appointment.get("locator") for appointment, signature in tower.pending_appointments]
        invalid_appointments = [appointment.get("locator") for appointment, signature in tower.invalid_appointments]
        values["pending_appointments"] = pending_appointments
        values["invalid_appointments"] = invalid_appointments
        towers_info["towers"].append({"id": tower_id, **values})

    return towers_info


@plugin.method("gettowerinfo", desc="List all towers registered towers.")
def get_tower_info(plugin, tower_id):
    """
    Gets information about a given tower. Data comes from disk (DB), so all stored data is provided.

    Args:
        plugin (:obj:`Plugin`): this plugin.
        tower_id: (:obj:`str`): the identifier of the queried tower.

    Returns:
        :obj:`dict`: a dictionary containing all data about the queried tower.
    """

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
    """
    Triggers a manual retry of a tower, tries to send all pending appointments to to it.

    Only works if the tower is unreachable or there's been a subscription error.

    Args:
        plugin (:obj:`Plugin`): this plugin.
        tower_id: (:obj:`str`): the identifier of the tower to be retried.

    Returns:

    """
    response = None
    plugin.wt_client.lock.acquire()
    tower = plugin.wt_client.towers.get(tower_id)

    if not tower:
        response = {"error": f"{tower_id} is not a registered tower"}

    # FIXME: it may be worth only allowing unreachable and forcing a retry on register_tower if the state is
    #        subscription error.
    if tower.status not in ["unreachable", "subscription error"]:
        response = {
            "error": f"Cannot retry tower. Expected tower status 'unreachable' or 'subscription error'. Received {tower.status}"
        }
    if not tower.pending_appointments:
        response = {"error": f"{tower_id} does not have pending appointments"}

    if not response:
        response = f"Retrying tower {tower_id}"
        plugin.log(response)
        plugin.wt_client.towers[tower_id].status = "temporarily unreachable"
        plugin.wt_client.retrier.temp_unreachable_towers.put(tower_id)

    plugin.wt_client.lock.release()
    return response


@plugin.hook("commitment_revocation")
def on_commitment_revocation(plugin, **kwargs):
    """
    Sends an appointment to all registered towers for every net commitment transaction.

    kwargs should contain the commitment identifier (commitment_txid) and the penalty transaction (penalty_tx)

    Args:
        plugin (:obj:`Plugin`): this plugin.
    """

    try:
        commitment_txid, penalty_tx = arg_parser.parse_add_appointment_arguments(kwargs)
        appointment = Appointment(
            locator=compute_locator(commitment_txid),
            encrypted_blob=Cryptographer.encrypt(penalty_tx, commitment_txid),
            to_self_delay=20,  # does not matter for now, any value 20-2^32-1 would do
        )
        signature = Cryptographer.sign(appointment.serialize(), plugin.wt_client.sk)

    except (InvalidParameter, EncryptionError, SignatureError) as e:
        plugin.log(str(e), level="warn")
        return {"result": "continue"}

    # Send appointment to the towers.
    # FIXME: sending the appointment to all registered towers atm. Some management would be nice.
    for tower_id, tower in plugin.wt_client.towers.items():
        tower_update = {}

        if tower.status == "misbehaving":
            continue

        try:
            if tower.status == "reachable":
                tower_signature, available_slots = add_appointment(
                    plugin, tower_id, tower, appointment.to_dict(), signature
                )
                tower_update["appointment"] = (appointment.locator, tower_signature)
                tower_update["available_slots"] = available_slots

            else:
                if tower.status in ["temporarily unreachable", "unreachable"]:
                    plugin.log(f"{tower_id} is {tower.status}. Adding {appointment.locator} to pending")
                elif tower.status == "subscription error":
                    plugin.log(f"There is a subscription issue with {tower_id}. Adding appointment to pending")

                tower_update["pending_appointment"] = (appointment.to_dict(), signature), "add"

        except SignatureError as e:
            tower_update["status"] = "misbehaving"
            tower_update["misbehaving_proof"] = {
                "appointment": appointment.to_dict(),
                "signature": e.kwargs.get("signature"),
                "recovered_id": e.kwargs.get("recovered_id"),
                "receipt": e.kwargs.get("receipt"),
            }

        except TowerConnectionError:
            # All TowerConnectionError are transitory. Connections are tried on register so URLs cannot be malformed.
            # Flag appointment for retry
            tower_update["status"] = "temporarily unreachable"
            plugin.log(f"Adding {appointment.locator} to pending")
            tower_update["pending_appointment"] = (appointment.to_dict(), signature), "add"
            tower_update["retry"] = True

        except TowerResponseError as e:
            tower_update["status"] = e.kwargs.get("status")

            if tower_update["status"] in ["temporarily unreachable", "subscription error"]:
                plugin.log(f"Adding {appointment.locator} to pending")
                tower_update["pending_appointment"] = (appointment.to_dict(), signature), "add"

                if tower_update["status"] == "temporarily unreachable":
                    tower_update["retry"] = True

            if e.kwargs.get("invalid_appointment"):
                tower_update["invalid_appointment"] = (appointment.to_dict(), signature)

        finally:
            # Update memory and TowersDB
            plugin.wt_client.update_tower_state(tower_id, tower_update)

            if tower_update.get("retry"):
                plugin.wt_client.retrier.temp_unreachable_towers.put(tower_id)

    return {"result": "continue"}


plugin.run()
