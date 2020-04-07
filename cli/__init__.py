import os

DATA_DIR = os.path.expanduser("~/.teos_cli/")
CONF_FILE_NAME = "teos_cli.conf"
LOG_PREFIX = "cli"

# Load config fields
DEFAULT_CONF = {
    "API_CONNECT": {"value": "localhost", "type": str},
    "API_PORT": {"value": 9814, "type": int},
    "LOG_FILE": {"value": "teos_cli.log", "type": str, "path": True},
    "APPOINTMENTS_FOLDER_NAME": {"value": "appointment_receipts", "type": str, "path": True},
    "CLI_PUBLIC_KEY": {"value": "cli_pk.der", "type": str, "path": True},
    "CLI_PRIVATE_KEY": {"value": "cli_sk.der", "type": str, "path": True},
    "TEOS_PUBLIC_KEY": {"value": "teos_pk.der", "type": str, "path": True},
}
