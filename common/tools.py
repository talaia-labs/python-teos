import re
import os
import logging
from common.constants import LOCATOR_LEN_HEX


def check_sha256_hex_format(value):
    """
    Checks if a given value is a 32-byte hex encoded string.

    Args:
        value(:mod:`str`): the value to be checked.

    Returns:
        :obj:`bool`: Whether or not the value matches the format.
    """
    return isinstance(value, str) and re.match(r"^[0-9A-Fa-f]{64}$", value) is not None


def check_locator_format(value):
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
        data_folder (:obj:`str`): the path of the folder
    """

    if not os.path.isdir(data_folder):
        os.makedirs(data_folder, exist_ok=True)


def extend_paths(base_path, config_fields):
    """
    Extends the relative paths of a given ``config_fields`` dictionary with a given ``base_path``.

    Paths in the config file are based on DATA_PATH, this method extends them so they are all absolute.

    Args:
        base_path (:obj:`str`): the base path to prepend the other paths.
        config_fields (:obj:`dict`): a dictionary of configuration fields containing a ``path`` flag, as follows:
            {"field0": {"value": value_from_conf_file, "path": True, ...}}

    """

    for key, field in config_fields.items():
        if field.get("path") is True:
            config_fields[key]["value"] = os.path.join(base_path, config_fields[key]["value"])


def setup_logging(log_file_path, log_name_prefix):
    """
    Setups a couple of loggers (console and file) given a prefix and a file path. The log names are:

    prefix | _file_log and prefix | _console_log

    Args:
        log_file_path (:obj:`str`): the path of the file to output the file log.
        log_name_prefix (:obj:`str`): the prefix to identify the log.
    """

    if not isinstance(log_file_path, str):
        print(log_file_path)
        raise ValueError("Wrong log file path.")

    if not isinstance(log_name_prefix, str):
        raise ValueError("Wrong log file name.")

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
