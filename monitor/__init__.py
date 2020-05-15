import os

MONITOR_DIR = os.getcwd() + "/monitor/"
MONITOR_CONF = "monitor.conf"

MONITOR_DEFAULT_CONF = {
    "ES_HOST": {"value": "", "type": str},
    "ES_PORT": {"value": 9200, "type": int},
    "CLOUD_ID": {"value": "", "type": str}, 
    "AUTH_USER": {"value": "user", "type": str},
    "AUTH_PW": {"value": "password", "type": str},
    "KIBANA_HOST": {"value": "localhost", "type": str},
    "KIBANA_PORT": {"value": "9243", "type": int},
}
