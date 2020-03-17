import os
import teos.conf as conf
from common.tools import check_conf_fields, setup_logging, extend_paths, setup_data_folder
from teos.utils.auth_proxy import AuthServiceProxy

HOST = "localhost"
PORT = 9814
LOG_PREFIX = "teos"

# Load config fields
conf_fields = {
    "BTC_RPC_USER": {"value": conf.BTC_RPC_USER, "type": str},
    "BTC_RPC_PASSWD": {"value": conf.BTC_RPC_PASSWD, "type": str},
    "BTC_RPC_HOST": {"value": conf.BTC_RPC_HOST, "type": str},
    "BTC_RPC_PORT": {"value": conf.BTC_RPC_PORT, "type": int},
    "BTC_NETWORK": {"value": conf.BTC_NETWORK, "type": str},
    "FEED_PROTOCOL": {"value": conf.FEED_PROTOCOL, "type": str},
    "FEED_ADDR": {"value": conf.FEED_ADDR, "type": str},
    "FEED_PORT": {"value": conf.FEED_PORT, "type": int},
    "DATA_FOLDER": {"value": conf.DATA_FOLDER, "type": str},
    "MAX_APPOINTMENTS": {"value": conf.MAX_APPOINTMENTS, "type": int},
    "EXPIRY_DELTA": {"value": conf.EXPIRY_DELTA, "type": int},
    "MIN_TO_SELF_DELAY": {"value": conf.MIN_TO_SELF_DELAY, "type": int},
    "SERVER_LOG_FILE": {"value": conf.SERVER_LOG_FILE, "type": str, "path": True},
    "TEOS_SECRET_KEY": {"value": conf.TEOS_SECRET_KEY, "type": str, "path": True},
    "DB_PATH": {"value": conf.DB_PATH, "type": str, "path": True},
}

# Expand user (~) if found and check fields are correct
conf_fields["DATA_FOLDER"]["value"] = os.path.expanduser(conf_fields["DATA_FOLDER"]["value"])
# Extend relative paths
conf_fields = extend_paths(conf_fields["DATA_FOLDER"]["value"], conf_fields)

# Sanity check fields and build config dictionary
config = check_conf_fields(conf_fields)

setup_data_folder(config.get("DATA_FOLDER"))
setup_logging(config.get("SERVER_LOG_FILE"), LOG_PREFIX)
