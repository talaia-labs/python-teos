import logging
from .logger import Logger

# PISA-SERVER
DEFAULT_PISA_API_SERVER = 'btc.pisa.watch'
DEFAULT_PISA_API_PORT = 9814

# PISA-CLI
CLIENT_LOG_FILE = 'pisa-cli.log'
APPOINTMENTS_FOLDER_NAME = 'appointments'

# CRYPTO
SUPPORTED_HASH_FUNCTIONS = ["SHA256"]
SUPPORTED_CIPHERS = ["AES-GCM-128"]

PISA_PUBLIC_KEY = "pisa_pk.pem"

# Configure logging
logging.basicConfig(format='%(message)s', level=logging.INFO, handlers=[
    logging.FileHandler(CLIENT_LOG_FILE),
    logging.StreamHandler()
])

logger = Logger("Client")
