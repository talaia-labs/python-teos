import os

DATA_DIR = os.path.expanduser("~/.teos_cli/")
CONF_FILE_NAME = "teos_cli.conf"

# Load config fields
DEFAULT_CONF = {
    "RPC_CONNECT": {"value": "localhost", "type": str},
    "RPC_PORT": {"value": 9000, "type": int},
    "LOG_FILE": {"value": "teos_cli.log", "type": str, "path": True},
}
