import pytest
from uuid import uuid4
from hashlib import sha256
from binascii import unhexlify

from pisa import c_logger
from pisa.block_processor import BlockProcessor
from test.unit.conftest import get_random_value_hex

c_logger.disabled = True

APPOINTMENT_COUNT = 100
TEST_SET_SIZE = 200


@pytest.fixture(scope='module')
def txids():
    return [get_random_value_hex(32) for _ in range(APPOINTMENT_COUNT)]


@pytest.fixture(scope='module')
def locator_uuid_map(txids):
    return {sha256(unhexlify(txid)).hexdigest(): uuid4().hex for txid in txids}


@pytest.fixture
def best_block_hash():
    return BlockProcessor.get_best_block_hash()


def test_get_best_block_hash(run_bitcoind, best_block_hash):
    # As long as bitcoind is running (or mocked in this case) we should always a block hash
    assert best_block_hash is not None and isinstance(best_block_hash, str)


def test_get_block(best_block_hash):
    # Getting a block from a block hash we are aware of should return data
    block = BlockProcessor.get_block(best_block_hash)

    # Checking that the received block has at least the fields we need
    # FIXME: We could be more strict here, but we'll need to add those restrictions to bitcoind_sim too
    assert isinstance(block, dict)
    assert block.get('hash') == best_block_hash and 'height' in block and 'previousblockhash' in block and 'tx' in block


def test_get_random_block():
    block = BlockProcessor.get_block(get_random_value_hex(32))

    assert block is None


def test_get_block_count():
    block_count = BlockProcessor.get_block_count()
    assert isinstance(block_count, int) and block_count >= 0


def test_potential_matches(txids, locator_uuid_map):
    potential_matches = BlockProcessor.get_potential_matches(txids, locator_uuid_map)

    # All the txids must match
    assert locator_uuid_map.keys() == potential_matches.keys()


def test_potential_matches_random(locator_uuid_map):
    txids = [get_random_value_hex(32) for _ in range(len(locator_uuid_map))]

    potential_matches = BlockProcessor.get_potential_matches(txids, locator_uuid_map)

    # None of the ids should match
    assert len(potential_matches) == 0


def test_potential_matches_random_data(locator_uuid_map):
    # The likelihood of finding a potential match with random data should be negligible
    txids = [get_random_value_hex(32) for _ in range(TEST_SET_SIZE)]

    potential_matches = BlockProcessor.get_potential_matches(txids, locator_uuid_map)

    # None of the txids should match
    assert len(potential_matches) == 0
