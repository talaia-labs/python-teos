import backoff
from threading import Thread

from common.exceptions import SignatureError

from net.http import add_appointment
from exceptions import TowerConnectionError, TowerResponseError


MAX_RETRIES = None


def check_retry(status):
    """
    Checks is the job needs to be retried. Jobs are retried if max_retries is not reached and the tower status is
    temporarily unreachable.

    Args:
        status (:obj:`str`): the tower status.

    Returns:
            :obj:`bool`: True is the status is "temporarily unreachable", False otherwise.
    """
    return status == "temporarily unreachable"


def on_backoff(details):
    """
    Function called when backing off after a retry. Logs data regarding the retry.
    Args:
        details: the retry details (check backoff library for more info).
    """
    plugin = details.get("args")[1]
    tower_id = details.get("args")[2]
    plugin.log(f"Retry {details.get('tries')} failed for tower {tower_id}, backing off")


def on_giveup(details):
    """
    Function called when giving up after the last retry. Logs data regarding the retry and flags the tower as
    unreachable.

    Args:
        details: the retry details (check backoff library for more info).
    """
    plugin = details.get("args")[1]
    tower_id = details.get("args")[2]

    plugin.log(f"Max retries reached, abandoning tower {tower_id}")

    tower_update = {"status": "unreachable"}
    plugin.wt_client.update_tower_state(tower_id, tower_update)


def set_max_retries(max_retries):
    """Workaround to set max retries from Retrier to the backoff.on_predicate decorator"""
    global MAX_RETRIES
    MAX_RETRIES = max_retries


def max_retries():
    """Workaround to set max retries from Retrier to the backoff.on_predicate decorator"""
    return MAX_RETRIES


class Retrier:
    """
    The Retrier is in charge of the retry process for appointments that were sent to towers that were temporarily
    unreachable.

    Args:
        max_retries (:obj:`int`): the maximum number of times that a tower will be retried.
        temp_unreachable_towers (:obj:`Queue`): a queue of temporarily unreachable towers populated by the plugin on
            failing to deliver an appointment.
    """

    def __init__(self, max_retries, temp_unreachable_towers):
        self.temp_unreachable_towers = temp_unreachable_towers
        set_max_retries(max_retries)

    def manage_retry(self, plugin):
        """
        Listens to the temporarily unreachable towers queue and creates a thread to manage each tower it gets.

        Args:
            plugin (:obj:`Plugin`): the plugin object.
        """

        while True:
            tower_id = self.temp_unreachable_towers.get()
            tower = plugin.wt_client.towers[tower_id]

            Thread(target=self.do_retry, args=[plugin, tower_id, tower], daemon=True).start()

    @backoff.on_predicate(backoff.expo, check_retry, max_tries=max_retries, on_backoff=on_backoff, on_giveup=on_giveup)
    def do_retry(self, plugin, tower_id, tower):
        """
        Retries to send a list of pending appointments to a temporarily unreachable tower. This function is managed by
        manage_retries and run in a different thread per tower.

        For every pending appointment the worker thread tries to send the data to the tower. If the tower keeps being
        unreachable, the job is retries up to MAX_RETRIES. If MAX_RETRIES is reached, the worker thread gives up and the
        tower is flagged as unreachable.

        Args:
            plugin (:obj:`Plugin`): the plugin object.
            tower_id (:obj:`str`): the id of the tower managed by the thread.
            tower: (:obj:`TowerSummary`): the tower data.

        Returns:
            :obj:`str`: the tower status if it is not reachable.
        """

        for appointment_dict, signature in plugin.wt_client.towers[tower_id].pending_appointments:
            tower_update = {}
            try:
                tower_signature, available_slots = add_appointment(plugin, tower_id, tower, appointment_dict, signature)
                tower_update["status"] = "reachable"
                tower_update["appointment"] = (appointment_dict.get("locator"), tower_signature)
                tower_update["available_slots"] = available_slots

            except SignatureError as e:
                tower_update["status"] = "misbehaving"
                tower_update["misbehaving_proof"] = {
                    "appointment": appointment_dict,
                    "signature": e.kwargs.get("signature"),
                    "recovered_id": e.kwargs.get("recovered_id"),
                }

            except TowerConnectionError:
                tower_update["status"] = "temporarily unreachable"

            except TowerResponseError as e:
                tower_update["status"] = e.kwargs.get("status")

                if e.kwargs.get("invalid_appointment"):
                    tower_update["invalid_appointment"] = (appointment_dict, signature)

            if tower_update["status"] in ["reachable", "misbehaving"]:
                tower_update["pending_appointment"] = ([appointment_dict, signature], "remove")

            if tower_update["status"] != "temporarily unreachable":
                # Update memory and TowersDB
                plugin.wt_client.update_tower_state(tower_id, tower_update)

            # Continue looping if reachable, return for either retry or stop otherwise
            if tower_update["status"] != "reachable":
                return tower_update.get("status")
