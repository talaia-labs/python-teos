import logging

# PISA-SERVER
DEFAULT_PISA_API_SERVER = "btc.pisa.watch"
DEFAULT_PISA_API_PORT = 9814

# PISA-CLI
CLIENT_LOG_FILE = "pisa-cli.log"
APPOINTMENTS_FOLDER_NAME = "appointments"

CLI_PUBLIC_KEY = "cli_pk.der"
CLI_PRIVATE_KEY = "cli_sk.der"
PISA_PUBLIC_KEY = "pisa_pk.der"

# Create the file logger
f_logger = logging.getLogger("cli_file_log")
f_logger.setLevel(logging.INFO)

fh = logging.FileHandler(CLIENT_LOG_FILE)
fh.setLevel(logging.INFO)
fh_formatter = logging.Formatter("%(message)s")
fh.setFormatter(fh_formatter)
f_logger.addHandler(fh)

# Create the console logger
c_logger = logging.getLogger("cli_console_log")
c_logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch_formatter = logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
ch.setFormatter(ch_formatter)
c_logger.addHandler(ch)
