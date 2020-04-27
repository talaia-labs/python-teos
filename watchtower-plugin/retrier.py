from tower_info import TowerInfo
from net.http import send_appointment
from exceptions import TowerConnectionError, TowerResponseError


class Retrier:
    def __init__(self, retry_delta, max_retries, temp_unreachable_towers):
        self.retry_delta = retry_delta
        self.max_retries = max_retries
        self.temp_unreachable_towers = temp_unreachable_towers
        self.retry_count = {}

    def do_retry(self, plugin):
        while True:
            tower_id = self.temp_unreachable_towers.get()
            tower_info = TowerInfo.from_dict(plugin.wt_client.db_manager.load_tower_record(tower_id))

            try:
                for appointment_dict, signature in plugin.wt_client.towers[tower_id]["pending_appointments"]:
                    plugin.log("Retrying: sending appointment to {}".format(tower_id))
                    response = send_appointment(tower_id, tower_info, appointment_dict, signature)
                    plugin.log("Appointment accepted and signed by {})".format(tower_id))
                    plugin.log("Remaining slots: {}".format(response.get("available_slots")))

                    tower_info.appointments[appointment_dict.get("locator")] = response.get("signature")
                    tower_info.available_slots = response.get("available_slots")

                    # Update memory and TowersDB
                    tower_info.pending_appointments.remove([appointment_dict, signature])
                    plugin.wt_client.db_manager.store_tower_record(tower_id, tower_info)
                    plugin.wt_client.towers[tower_id] = tower_info.get_summary()

                    if tower_id in self.retry_count:
                        self.retry_count.pop(tower_id)

                tower_info.status = "reachable"
                plugin.wt_client.towers[tower_id]["status"] = "reachable"
                plugin.wt_client.db_manager.store_tower_record(tower_id, tower_info)

            except TowerConnectionError:
                if tower_id not in self.retry_count:
                    self.retry_count[tower_id] = 1
                else:
                    plugin.log("Retry {} failed for tower {}, backing off".format(self.retry_count[tower_id], tower_id))
                    self.retry_count[tower_id] += 1

                if self.retry_count[tower_id] <= self.max_retries:
                    self.temp_unreachable_towers.put(tower_id)
                else:
                    plugin.log("Max retries reached, abandoning tower {}".format(tower_id))
                    self.retry_count.pop(tower_id)

                    tower_info.status = "unreachable"
                    plugin.wt_client.towers[tower_id]["status"] = "unreachable"
                    plugin.wt_client.db_manager.store_tower_record(tower_id, tower_info)

            except TowerResponseError as e:
                # FIXME: deal with tower errors, such as no available slots
                plugin.log(str(e))
