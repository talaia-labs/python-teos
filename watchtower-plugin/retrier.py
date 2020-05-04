import backoff
from threading import Thread

from common.exceptions import SignatureError

from net.http import add_appointment
from exceptions import TowerConnectionError, TowerResponseError


MAX_RETRIES = None


def on_backoff(details):
    plugin = details.get("args")[1]
    tower_id = details.get("args")[2]
    plugin.log(f"Retry {details.get('tries')} failed for tower {tower_id}, backing off")


def on_giveup(details):
    plugin = details.get("args")[1]
    tower_id = details.get("args")[2]

    plugin.log(f"Max retries reached, abandoning tower {tower_id}")

    tower_update = {"status": "unreachable"}
    plugin.wt_client.update_tower_state(tower_id, tower_update)


def set_max_retries(max_retries):
    global MAX_RETRIES
    MAX_RETRIES = max_retries


def max_retries():
    return MAX_RETRIES


class Retrier:
    def __init__(self, max_retries, temp_unreachable_towers):
        self.temp_unreachable_towers = temp_unreachable_towers
        set_max_retries(max_retries)

    def manage_retry(self, plugin):
        while True:
            tower_id = self.temp_unreachable_towers.get()
            tower = plugin.wt_client.towers[tower_id]

            Thread(target=self.do_retry, args=[plugin, tower_id, tower], daemon=True).start()

    @backoff.on_predicate(
        backoff.expo,
        lambda x: x == "temporarily unreachable",
        max_tries=max_retries,
        on_backoff=on_backoff,
        on_giveup=on_giveup,
    )
    def do_retry(self, plugin, tower_id, tower):
        for appointment_dict, signature in plugin.wt_client.towers[tower_id]["pending_appointments"]:
            tower_update = {}
            try:
                tower_signature, available_slots = add_appointment(plugin, tower_id, tower, appointment_dict, signature)
                tower_update["status"] = "reachable"
                tower_update["appointment"] = (appointment_dict.get("locator"), tower_signature)
                tower_update["available_slots"] = available_slots

            except SignatureError as e:
                tower_update["status"] = "misbehaving"
                tower_update["invalid_appointment"] = (appointment_dict, e.kwargs.get("signature"))

            except TowerConnectionError:
                tower_update["status"] = "temporarily unreachable"

            except TowerResponseError as e:
                tower_update["status"] = e.kwargs.get("status")

            if tower_update["status"] in ["reachable", "misbehaving"]:
                tower_update["pending_appointment"] = ([appointment_dict, signature], "remove")

            if tower_update["status"] != "temporarily unreachable":
                # Update memory and TowersDB
                plugin.wt_client.update_tower_state(tower_id, tower_update)

            # Continue looping if reachable, return for either retry or stop otherwise
            if tower_update["status"] != "reachable":
                return tower_update.get("status")
