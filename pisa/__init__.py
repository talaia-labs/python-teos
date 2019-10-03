import logging

from pisa.utils.auth_proxy import AuthServiceProxy
import pisa.conf as conf


HOST = 'localhost'
PORT = 9814

# Configure logging
logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO, handlers=[
    logging.FileHandler(conf.SERVER_LOG_FILE),
    logging.StreamHandler()
])

# Create RPC connection with bitcoind
# TODO: Check if a long lived connection like this may create problems (timeouts)
bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (conf.BTC_RPC_USER, conf.BTC_RPC_PASSWD, conf.BTC_RPC_HOST,
                                                       conf.BTC_RPC_PORT))

