import logging

from pisa.utils.auth_proxy import AuthServiceProxy
import pisa.conf as conf

HOST = 'localhost'
PORT = 9814

# Configure logging
logging.basicConfig(format='%(message)s', level=logging.INFO, handlers=[
    logging.FileHandler(conf.SERVER_LOG_FILE),
    logging.StreamHandler()
])
