import os

MONITOR_DIR = os.path.expanduser("~/.teos_monitor/")
MONITOR_CONF = "monitor.conf"

MONITOR_DEFAULT_CONF = {
    "ES_HOST": {"value": "localhost", "type": str},
    "ES_PORT": {"value": 9200, "type": int},
    "KIBANA_HOST": {"value": "localhost", "type": str},
    "KIBANA_PORT": {"value": 5601, "type": int},
    "API_BIND": {"value": "localhost", "type": str},
    "API_PORT": {"value": 9814, "type": int},
}
