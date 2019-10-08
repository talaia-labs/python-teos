import logging
import json
import time

from pisa.utils.auth_proxy import AuthServiceProxy
import pisa.conf as conf

HOST = 'localhost'
PORT = 9814


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

    def info(msg, **kwargs):
        logging.info(StructuredMessage(self._add_prefix(msg), **kwargs))

    def debug(msg, **kwargs):
        logging.debug(StructuredMessage(self._add_prefix(msg), **kwargs))

    def error(msg, **kwargs):
        logging.error(StructuredMessage(self._add_prefix(msg), **kwargs))

# Configure logging
logging.basicConfig(format='%(message)s', level=logging.INFO, handlers=[
    logging.FileHandler(conf.SERVER_LOG_FILE),
    logging.StreamHandler()
])

# Create RPC connection with bitcoind
# TODO: Check if a long lived connection like this may create problems (timeouts)
bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (conf.BTC_RPC_USER, conf.BTC_RPC_PASSWD, conf.BTC_RPC_HOST,
                                                       conf.BTC_RPC_PORT))
