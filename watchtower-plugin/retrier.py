import backoff
from threading import Thread

from tower_info import TowerInfo
from net.http import add_appointment


MAX_RETRIES = None


def on_backoff(details):
    plugin = details.get("args")[1]
    tower_id = details.get("args")[2]
    plugin.log("Retry {} failed for tower {}, backing off".format(details.get("tries"), tower_id))


def on_giveup(details):
    plugin = details.get("args")[1]
    tower_id = details.get("args")[2]
    tower_info = details.get("args")[3]

    plugin.log("Max retries reached, abandoning tower {}".format(tower_id))

    tower_info.status = "unreachable"
    plugin.wt_client.towers[tower_id]["status"] = "unreachable"
    plugin.wt_client.db_manager.store_tower_record(tower_id, tower_info)


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
            tower_info = TowerInfo.from_dict(plugin.wt_client.db_manager.load_tower_record(tower_id))

            Thread(target=self.do_retry, args=[plugin, tower_id, tower_info], daemon=True).start()

    @backoff.on_predicate(
        backoff.expo,
        lambda x: x == "temporarily unreachable",
        max_tries=max_retries,
        on_backoff=on_backoff,
        on_giveup=on_giveup,
    )
    def do_retry(self, plugin, tower_id, tower_info):
        for appointment_dict, signature in plugin.wt_client.towers[tower_id]["pending_appointments"]:
            status = add_appointment(plugin, tower_id, tower_info, appointment_dict, signature)

            if status in ["reachable", "misbehaving"]:
                tower_info.pending_appointments.remove([appointment_dict, signature])

                # Update memory and TowersDB
                plugin.wt_client.update_tower_state(tower_id, tower_info)

            else:
                return status
