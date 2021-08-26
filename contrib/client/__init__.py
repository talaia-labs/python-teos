import os

version_info = (0, 1, 1)
__version__ = ".".join([str(v) for v in version_info])

DATA_DIR = os.path.expanduser("~/.teos_client/")
CONF_FILE_NAME = "teos_client.conf"

# Load config fields
DEFAULT_CONF = {
    "API_CONNECT": {"value": "localhost", "type": str},
    "API_PORT": {"value": 9814, "type": int},
    "APPOINTMENTS_FOLDER_NAME": {"value": "appointment_receipts", "type": str, "path": True},
    "USER_PRIVATE_KEY": {"value": "user_sk.der", "type": str, "path": True},
    "TEOS_PUBLIC_KEY": {"value": "teos_pk.der", "type": str, "path": True},
    "SOCKS_PORT": {"value": 9050, "type": int},
}
