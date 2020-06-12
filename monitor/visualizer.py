import json
import requests

from monitor.data_loader import LOG_PREFIX
from common.logger import Logger

from monitor.visualizations import index_pattern, visualizations, dashboard

logger = Logger(actor="Visualizer", log_name_prefix=LOG_PREFIX)


class Visualizer:
    def __init__(self, kibana_host, kibana_port, max_users):
        self.kibana_endpoint = "http://{}:{}".format(kibana_host, kibana_port)
        self.saved_obj_endpoint = "{}/api/saved_objects/".format(self.kibana_endpoint)
        self.headers = headers = { 
            "Content-Type": "application/json",
            "kbn-xsrf": "true"
        }
        self.max_users = max_users

    def create_dashboard(self):
        index_id = None

        # Find index pattern id if it exists. If it does not, create one to pull Elasticsearch data into Kibana.
        index_pattern_json = self.find("index-pattern", "title", index_pattern.get("attributes").get("title"))

        if index_pattern_json.get("total") == 0:
            resp = self.create_saved_object("index-pattern", index_pattern.get("attributes"), [])
            index_id = resp.get("id")
        else:
            index_id = index_pattern_json.get("saved_objects")[0].get("id") 

        visuals = []
        panelCount = 0

        for key, value in visualizations.items(): 
            if not self.exists("visualization", "title", value.get("attributes").get("title")): 
                if key == "available_user_slots_visual":
                    visState_json = json.loads(value["attributes"]["visState"])
                    visState_json["params"]["gauge"]["colorsRange"][0]["to"] = self.max_users
                    value["attributes"]["visState"] = json.dumps(visState_json)

                for ref in value.get("references"): 
                    ref["id"] = index_id

                resp = self.create_saved_object("visualization", value.get("attributes"), value.get("references"))

                visual_info = {
                    "name": "panel_{}".format(panelCount),
                    "id": resp.get("id"),
                    "type": "visualization"
                }                
                visuals.append(visual_info)
                panelCount += 1

        if not self.exists("dashboard", "title", dashboard.get("attributes").get("title")):
            panels_JSON = json.loads(dashboard["attributes"]["panelsJSON"])

            for i, panel in enumerate(panels_JSON):
                visual_id = visuals[i].get("id")
                panel["gridData"]["i"] = visual_id 
                panel["panelIndex"] = visual_id

            dashboard["attributes"]["panelsJSON"] = json.dumps(panels_JSON)

            self.create_saved_object("dashboard", dashboard.get("attributes"), visuals) 

    def find(self, obj_type, search_field, search):
        endpoint = "{}{}".format(self.saved_obj_endpoint, "_find")

        data = {
            "type": obj_type,
            "search_fields": search_field,
            "search": search,
            "default_search_operator": "AND"
        }

        response = requests.get(endpoint, params=data, headers=self.headers)

        return response.json()
 

    def exists(self, obj_type, search_field, search):
        endpoint = "{}{}".format(self.saved_obj_endpoint, "_find")

        data = { 
            "type": obj_type,
            "search_fields": search_field,
            "search": search,
            "default_search_operator": "AND"
        }

        response = requests.get(endpoint, params=data, headers=self.headers) 

        response_json = response.json()

        if response.status_code == 200:
            if response_json.get("total") == 0:
                return False 
            else:
                return True 

    def create_saved_object(self, obj_type, attributes, references):
        endpoint = "{}{}".format(self.saved_obj_endpoint, obj_type)

        data = { 
            "attributes": attributes
        }

        if len(references) > 0:
            data["references"] = references

        data = json.dumps(data)

        response = requests.post(endpoint, data=data, headers=self.headers)

        # log when an item is created.
        logger.info("New Kibana saved object was created")

        return response.json()
