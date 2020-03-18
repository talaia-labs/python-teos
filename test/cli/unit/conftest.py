import pytest
import random


@pytest.fixture(scope="session", autouse=True)
def prng_seed():
    random.seed(0)


def get_random_value_hex(nbytes):
    pseudo_random_value = random.getrandbits(8 * nbytes)
    prv_hex = "{:x}".format(pseudo_random_value)
    return prv_hex.zfill(2 * nbytes)
