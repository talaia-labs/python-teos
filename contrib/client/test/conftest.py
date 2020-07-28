import pytest
import random

from contrib.client import DEFAULT_CONF

from common.config_loader import ConfigLoader


@pytest.fixture(scope="session", autouse=True)
def prng_seed():
    random.seed(0)


def get_random_value_hex(nbytes):
    pseudo_random_value = random.getrandbits(8 * nbytes)
    prv_hex = "{:x}".format(pseudo_random_value)
    return prv_hex.zfill(2 * nbytes)


def get_config():
    config_loader = ConfigLoader(".", "teos_client.conf", DEFAULT_CONF, {})
    config = config_loader.build_config()

    return config
