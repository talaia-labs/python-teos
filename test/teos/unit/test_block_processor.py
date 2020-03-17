import pytest

from teos.block_processor import BlockProcessor
from test.teos.unit.conftest import get_random_value_hex, generate_block, generate_blocks, fork


hex_tx = (
    "0100000001c997a5e56e104102fa209c6a852dd90660a20b2d9c352423edce25857fcd3704000000004847304402"
    "204e45e16932b8af514961a1d3a1a25fdf3f4f7732e9d624c6c61548ab5fb8cd410220181522ec8eca07de4860a4"
    "acdd12909d831cc56cbbac4622082221a8768d1d0901ffffffff0200ca9a3b00000000434104ae1a62fe09c5f51b"
    "13905f07f06b99a2f7159b2225f374cd378d71302fa28414e7aab37397f554a7df5f142c21c1b7303b8a0626f1ba"
    "ded5c72a704f7e6cd84cac00286bee0000000043410411db93e1dcdb8a016b49840f8c53bc1eb68a382e97b1482e"
    "cad7b148a6909a5cb2e0eaddfb84ccf9744464f82e160bfa9b8b64f9d4c03f999b8643f656b412a3ac00000000"
)


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
    assert block.get("hash") == best_block_hash and "height" in block and "previousblockhash" in block and "tx" in block


def test_get_random_block():
    block = BlockProcessor.get_block(get_random_value_hex(32))

    assert block is None


def test_get_block_count():
    block_count = BlockProcessor.get_block_count()
    assert isinstance(block_count, int) and block_count >= 0


def test_decode_raw_transaction():
    # We cannot exhaustively test this (we rely on bitcoind for this) but we can try to decode a correct transaction
    assert BlockProcessor.decode_raw_transaction(hex_tx) is not None


def test_decode_raw_transaction_invalid():
    # Same but with an invalid one
    assert BlockProcessor.decode_raw_transaction(hex_tx[::-1]) is None


def test_get_missed_blocks():
    target_block = BlockProcessor.get_best_block_hash()

    # Generate some blocks and store the hash in a list
    missed_blocks = []
    for _ in range(5):
        generate_block()
        missed_blocks.append(BlockProcessor.get_best_block_hash())

    # Check what we've missed
    assert BlockProcessor.get_missed_blocks(target_block) == missed_blocks

    # We can see how it does not work if we replace the target by the first element in the list
    block_tip = missed_blocks[0]
    assert BlockProcessor.get_missed_blocks(block_tip) != missed_blocks

    # But it does again if we skip that block
    assert BlockProcessor.get_missed_blocks(block_tip) == missed_blocks[1:]


def test_get_distance_to_tip():
    target_distance = 5

    target_block = BlockProcessor.get_best_block_hash()

    # Mine some blocks up to the target distance
    generate_blocks(target_distance)

    # Check if the distance is properly computed
    assert BlockProcessor.get_distance_to_tip(target_block) == target_distance


def test_is_block_in_best_chain():
    best_block_hash = BlockProcessor.get_best_block_hash()
    best_block = BlockProcessor.get_block(best_block_hash)

    assert BlockProcessor.is_block_in_best_chain(best_block_hash)

    fork(best_block.get("previousblockhash"))
    generate_blocks(2)

    assert not BlockProcessor.is_block_in_best_chain(best_block_hash)


def test_find_last_common_ancestor():
    ancestor = BlockProcessor.get_best_block_hash()
    generate_blocks(3)
    best_block_hash = BlockProcessor.get_best_block_hash()

    # Create a fork (forking creates a block if the mock is set by events)
    fork(ancestor)

    # Create another block to make the best tip change (now both chains are at the same height)
    generate_blocks(5)

    # The last common ancestor between the old best and the new best should be the "ancestor"
    last_common_ancestor, dropped_txs = BlockProcessor.find_last_common_ancestor(best_block_hash)
    assert last_common_ancestor == ancestor
    assert len(dropped_txs) == 3
