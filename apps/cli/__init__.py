import logging
import json
import time

# PISA-SERVER
DEFAULT_PISA_API_SERVER = 'btc.pisa.watch'
DEFAULT_PISA_API_PORT = 9814

# PISA-CLI
CLIENT_LOG_FILE = 'pisa-cli.log'

# CRYPTO
SUPPORTED_HASH_FUNCTIONS = ["SHA256"]
SUPPORTED_CIPHERS = ["AES-GCM-128"]

PISA_PUBLIC_KEY = "pisa_pk.pem"

# Configure logging
logging.basicConfig(format='%(message)s', level=logging.INFO, handlers=[
    logging.FileHandler(CLIENT_LOG_FILE),
    logging.StreamHandler()
])


class StructuredMessage(object):
    def __init__(self, message, **kwargs):
        self.message = message
        self.time = time.asctime()
        self.kwargs = kwargs

    def __str__(self):
        return json.dumps({**self.kwargs, "message": self.message, "time": self.time})


class Logger(object):
    def __init__(self, actor=None):
        self.actor = actor

    def _add_prefix(self, msg):
        return msg if self.actor is None else "[{}] {}".format(self.actor, msg)

    def info(self, msg, **kwargs):
        logging.info(StructuredMessage(self._add_prefix(msg), actor=self.actor, **kwargs))

    def debug(self, msg, **kwargs):
        logging.debug(StructuredMessage(self._add_prefix(msg), actor=self.actor, **kwargs))

    def error(self, msg, **kwargs):
        logging.error(StructuredMessage(self._add_prefix(msg), actor=self.actor, **kwargs))

    def warning(self, msg, **kwargs):
        logging.warning(StructuredMessage(self._add_prefix(msg), actor=self.actor, **kwargs))


logger = Logger("Client")