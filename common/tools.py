import re
import logging
from pathlib import Path
from common.constants import LOCATOR_LEN_HEX


def is_compressed_pk(value):
    """
    Checks if a given value is a 33-byte hex-encoded string starting by 02 or 03.

    Args:
        value(:obj:`str`): the value to be checked.

    Returns:
        :obj:`bool`: Whether or not the value matches the format.
    """

    return isinstance(value, str) and re.match(r"^0[2-3][0-9A-Fa-f]{64}$", value) is not None


def is_256b_hex_str(value):
    """
    Checks if a given value is a 32-byte hex encoded string.

    Args:
        value(:mod:`str`): the value to be checked.

    Returns:
        :obj:`bool`: Whether or not the value matches the format.
    """
    return isinstance(value, str) and re.match(r"^[0-9A-Fa-f]{64}$", value) is not None


def is_locator(value):
    """
    Checks if a given value is a 16-byte hex encoded string.

    Args:
        value(:mod:`str`): the value to be checked.

    Returns:
        :obj:`bool`: Whether or not the value matches the format.
    """
    return isinstance(value, str) and re.match(r"^[0-9A-Fa-f]{32}$", value) is not None


def compute_locator(tx_id):
    """
    Computes an appointment locator given a transaction id.
    Args:
        tx_id (:obj:`str`): the transaction id used to compute the locator.
    Returns:
       :obj:`str`: The computed locator.
    """

    return tx_id[:LOCATOR_LEN_HEX]


def setup_data_folder(data_folder):
    """
    Create a data folder for either the client or the server side if the folder does not exists.

    Args:
        data_folder (:obj:`str`): the path of the folder.
    """

    Path(data_folder).mkdir(parents=True, exist_ok=True)


def setup_logging(log_file_path, log_name_prefix):
    """
    Setups a couple of loggers (console and file) given a prefix and a file path.

    The log names are:

        prefix | _file_log
        prefix | _console_log

    Args:
        log_file_path (:obj:`str`): the path of the file to output the file log.
        log_name_prefix (:obj:`str`): the prefix to identify the log.
    """

    if not isinstance(log_file_path, str):
        print(log_file_path)
        raise ValueError("Wrong log file path")

    if not isinstance(log_name_prefix, str):
        raise ValueError("Wrong log file name")

    # Create the file logger
    f_logger = logging.getLogger("{}_file_log".format(log_name_prefix))
    f_logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(log_file_path)
    fh.setLevel(logging.DEBUG)
    fh_formatter = logging.Formatter("%(message)s")
    fh.setFormatter(fh_formatter)
    f_logger.addHandler(fh)

    # Create the console logger
    c_logger = logging.getLogger("{}_console_log".format(log_name_prefix))
    c_logger.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter("%(message)s.", "%Y-%m-%d %H:%M:%S")
    ch.setFormatter(ch_formatter)
    c_logger.addHandler(ch)
