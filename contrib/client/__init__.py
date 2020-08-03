import os

DATA_DIR = os.path.expanduser("~/.teos_client/")
CONF_FILE_NAME = "teos_client.conf"

# Load config fields
DEFAULT_CONF = {
    "API_CONNECT": {"value": "localhost", "type": str},
    "API_PORT": {"value": 9814, "type": int},
    "LOG_FILE": {"value": "teos_client.log", "type": str, "path": True},
    "APPOINTMENTS_FOLDER_NAME": {"value": "appointment_receipts", "type": str, "path": True},
    "USER_PRIVATE_KEY": {"value": "user_sk.der", "type": str, "path": True},
    "TEOS_PUBLIC_KEY": {"value": "teos_pk.der", "type": str, "path": True},
}
