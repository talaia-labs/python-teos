import logging
from apps.cli.logger import Logger

# PISA-SERVER
DEFAULT_PISA_API_SERVER = "btc.pisa.watch"
DEFAULT_PISA_API_PORT = 9814

# PISA-CLI
CLIENT_LOG_FILE = "pisa-cli.log"
APPOINTMENTS_FOLDER_NAME = "appointments"

CLI_PUBLIC_KEY = "cli_pk.der"
CLI_PRIVATE_KEY = "cli_sk.der"
PISA_PUBLIC_KEY = "pisa_pk.der"

# Configure logging
logging.basicConfig(
    format="%(message)s", level=logging.INFO, handlers=[logging.FileHandler(CLIENT_LOG_FILE), logging.StreamHandler()]
)

logger = Logger("Client")
