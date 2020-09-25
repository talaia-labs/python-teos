import os
from common.constants import MAINNET_RPC_PORT

version_info = (0, 1, 1)
__version__ = ".".join([str(v) for v in version_info])

DATA_DIR = os.path.expanduser("~/.teos/")
CONF_FILE_NAME = "teos.conf"
DEFAULT_CONF = {
    "API_BIND": {"value": "localhost", "type": str},
    "API_PORT": {"value": 9814, "type": int},
    "RPC_BIND": {"value": "localhost", "type": str},
    "RPC_PORT": {"value": 8814, "type": int},
    "BTC_RPC_USER": {"value": "user", "type": str},
    "BTC_RPC_PASSWORD": {"value": "passwd", "type": str},
    "BTC_RPC_CONNECT": {"value": "127.0.0.1", "type": str},
    "BTC_RPC_PORT": {"value": MAINNET_RPC_PORT, "type": int},
    "BTC_NETWORK": {"value": "mainnet", "type": str},
    "BTC_FEED_PROTOCOL": {"value": "tcp", "type": str},
    "BTC_FEED_CONNECT": {"value": "localhost", "type": str},
    "BTC_FEED_PORT": {"value": 28332, "type": int},
    "DAEMON": {"value": False, "type": bool},
    "MAX_APPOINTMENTS": {"value": 1000000, "type": int},
    "SUBSCRIPTION_SLOTS": {"value": 100, "type": int},
    "SUBSCRIPTION_DURATION": {"value": 4320, "type": int},
    "EXPIRY_DELTA": {"value": 6, "type": int},
    "MIN_TO_SELF_DELAY": {"value": 20, "type": int},
    "LOCATOR_CACHE_SIZE": {"value": 6, "type": int},
    "OVERWRITE_KEY": {"value": False, "type": bool},
    "WSGI": {"value": "gunicorn", "type": str},
    "LOG_FILE": {"value": "teos.log", "type": str, "path": True},
    "TEOS_SECRET_KEY": {"value": "teos_sk.der", "type": str, "path": True},
    "APPOINTMENTS_DB_PATH": {"value": "appointments", "type": str, "path": True},
    "USERS_DB_PATH": {"value": "users", "type": str, "path": True},
    "INTERNAL_API_HOST": {"value": "localhost", "type": str},
    "INTERNAL_API_PORT": {"value": 50051, "type": int},
    "INTERNAL_API_WORKERS": {"value": 10, "type": int},
}
