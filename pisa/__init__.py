import logging

from pisa.utils.auth_proxy import AuthServiceProxy
import pisa.conf as conf

HOST = 'localhost'
PORT = 9814

# Create the file logger
f_logger = logging.getLogger('pisa_file_log')
f_logger.setLevel(logging.INFO)

fh = logging.FileHandler(conf.SERVER_LOG_FILE)
fh.setLevel(logging.INFO)
fh_formatter = logging.Formatter('%(message)s')
fh.setFormatter(fh_formatter)
f_logger.addHandler(fh)

# Create the console logger
c_logger = logging.getLogger('pisa_console_log')
c_logger.setLevel(logging.INFO)

ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch_formatter = logging.Formatter('%(asctime)s %(message)s', '%Y-%m-%d %H:%M:%S')
ch.setFormatter(ch_formatter)
c_logger.addHandler(ch)
