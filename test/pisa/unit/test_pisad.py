import importlib
import os
import pytest
from pathlib import Path
from shutil import copyfile

from pisa.pisad import load_config

test_conf_file_path = os.getcwd() + "/test/pisa/unit/test_conf.py"


def test_load_config():
    # Copy the sample-conf.py file to use as a test config file.
    copyfile(os.getcwd() + "/pisa/sample_conf.py", test_conf_file_path)

    import test.pisa.unit.test_conf as conf

    # If the file has all the correct fields and data, it should return a dict.
    conf_dict = load_config(conf)
    assert type(conf_dict) == dict

    # Delete the file.
    os.remove(test_conf_file_path)


def test_bad_load_config():
    # Create a messed up version of the file that should throw an error.
    with open(test_conf_file_path, "w") as f:
        f.write('# bitcoind\nBTC_RPC_USER = 0000\nBTC_RPC_PASSWD = "password"\nBTC_RPC_HOST = 000')

    import test.pisa.unit.test_conf as conf

    importlib.reload(conf)

    with pytest.raises(Exception):
        conf_dict = load_config(conf)

    os.remove(test_conf_file_path)


def test_empty_load_config():
    # Create an empty version of the file that should throw an error.
    open(test_conf_file_path, "a")

    import test.pisa.unit.test_conf as conf

    importlib.reload(conf)

    with pytest.raises(Exception):
        conf_dict = load_config(conf)

    os.remove(test_conf_file_path)
