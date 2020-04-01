import os

HOST = "localhost"
PORT = 9814
DATA_DIR = os.path.expanduser("~/.teos/")
CONF_FILE_NAME = "teos.conf"
LOG_PREFIX = "teos"

# Default conf fields
DEFAULT_CONF = {
    "BTC_RPC_USER": {"value": "user", "type": str},
    "BTC_RPC_PASSWORD": {"value": "passwd", "type": str},
    "BTC_RPC_CONNECT": {"value": "127.0.0.1", "type": str},
    "BTC_RPC_PORT": {"value": 8332, "type": int},
    "BTC_NETWORK": {"value": "mainnet", "type": str},
    "FEED_PROTOCOL": {"value": "tcp", "type": str},
    "FEED_CONNECT": {"value": "127.0.0.1", "type": str},
    "FEED_PORT": {"value": 28332, "type": int},
    "MAX_APPOINTMENTS": {"value": 1000000, "type": int},
    "DEFAULT_SLOTS": {"value": 100, "type": int},
    "EXPIRY_DELTA": {"value": 6, "type": int},
    "MIN_TO_SELF_DELAY": {"value": 20, "type": int},
    "LOG_FILE": {"value": "teos.log", "type": str, "path": True},
    "TEOS_SECRET_KEY": {"value": "teos_sk.der", "type": str, "path": True},
    "APPOINTMENTS_DB_PATH": {"value": "appointments", "type": str, "path": True},
}
