import pytest
from threading import Event

from teos.block_processor import BlockProcessor
from teos.watcher import InvalidTransactionFormat

from test.teos.conftest import generate_blocks, fork
from test.teos.unit.conftest import (
    get_random_value_hex,
    bitcoind_connect_params,
    wrong_bitcoind_connect_params,
    run_test_command_bitcoind_crash,
    run_test_blocking_command_bitcoind_crash,
)


hex_tx = (
    "0100000001c997a5e56e104102fa209c6a852dd90660a20b2d9c352423edce25857fcd3704000000004847304402"
    "204e45e16932b8af514961a1d3a1a25fdf3f4f7732e9d624c6c61548ab5fb8cd410220181522ec8eca07de4860a4"
    "acdd12909d831cc56cbbac4622082221a8768d1d0901ffffffff0200ca9a3b00000000434104ae1a62fe09c5f51b"
    "13905f07f06b99a2f7159b2225f374cd378d71302fa28414e7aab37397f554a7df5f142c21c1b7303b8a0626f1ba"
    "ded5c72a704f7e6cd84cac00286bee0000000043410411db93e1dcdb8a016b49840f8c53bc1eb68a382e97b1482e"
    "cad7b148a6909a5cb2e0eaddfb84ccf9744464f82e160bfa9b8b64f9d4c03f999b8643f656b412a3ac00000000"
)


@pytest.fixture
def block_processor(run_bitcoind):
    bitcoind_reachable = Event()
    bitcoind_reachable.set()
    return BlockProcessor(bitcoind_connect_params, bitcoind_reachable)


@pytest.fixture
def block_processor_wrong_connection():
    bitcoind_reachable = Event()
    bitcoind_reachable.set()
    return BlockProcessor(wrong_bitcoind_connect_params, bitcoind_reachable)


def test_get_best_block_hash(block_processor):
    # As long as bitcoind is running we should always get a block hash
    best_block_hash = block_processor.get_best_block_hash()
    assert best_block_hash is not None and isinstance(best_block_hash, str)


def test_get_block(block_processor):
    # Getting a block from a block hash we are aware of should return data
    best_block_hash = block_processor.get_best_block_hash()
    block = block_processor.get_block(best_block_hash)

    # Checking that the received block has at least the fields we need
    assert isinstance(block, dict)
    assert block.get("hash") == best_block_hash and "height" in block and "previousblockhash" in block and "tx" in block


def test_get_random_block(block_processor):
    # Trying to query a random block should return None
    block = block_processor.get_block(get_random_value_hex(32))

    assert block is None


def test_get_block_count(block_processor):
    # We should be able to get the block count as long as bitcoind is reachable
    block_count = block_processor.get_block_count()
    assert isinstance(block_count, int) and block_count >= 0


def test_decode_raw_transaction(block_processor):
    # Decoding a raw transaction should return a dictionary.
    # We cannot exhaustively test this (we rely on bitcoind for this) but we can try to decode a correct transaction
    assert isinstance(block_processor.decode_raw_transaction(hex_tx), dict)


def test_decode_raw_transaction_invalid(block_processor):
    # Decoding an invalid raw transaction should raise
    with pytest.raises(InvalidTransactionFormat):
        block_processor.decode_raw_transaction(hex_tx[::-1])


def test_get_missed_blocks(block_processor):
    # get_missed_blocks returns the list of blocks from a given block hash to the chain tip
    target_block = block_processor.get_best_block_hash()

    # Generate some blocks and store the hash in a list
    missed_blocks = generate_blocks(5)

    # Check what we've missed
    assert block_processor.get_missed_blocks(target_block) == missed_blocks

    # We can see how it does not work if we replace the target by the first element in the list
    block_tip = missed_blocks[0]
    assert block_processor.get_missed_blocks(block_tip) != missed_blocks

    # But it does again if we skip that block
    assert block_processor.get_missed_blocks(block_tip) == missed_blocks[1:]


def test_get_distance_to_tip(block_processor):
    # get_distance_to_tip returns how many blocks the best chain contains from a given block hash to the best tip
    target_distance = 5

    target_block = block_processor.get_best_block_hash()

    # Mine some blocks up to the target distance
    generate_blocks(target_distance)

    # Check if the distance is properly computed
    assert block_processor.get_distance_to_tip(target_block) == target_distance


def test_is_block_in_best_chain(block_processor):
    # is_block_in_best_chain returns whether a given block hash is in the best chain

    # Testing it with the chain tip should return True
    best_block_hash = block_processor.get_best_block_hash()
    best_block = block_processor.get_block(best_block_hash)

    assert block_processor.is_block_in_best_chain(best_block_hash)

    # Forking the chain and trying the old best tip again should return False
    fork(best_block.get("previousblockhash"), 2)
    assert not block_processor.is_block_in_best_chain(best_block_hash)


def test_find_last_common_ancestor(block_processor):
    # find_last_common_ancestor finds the last common block between the best tip and a given block
    ancestor = block_processor.get_best_block_hash()
    blocks = generate_blocks(3)
    best_block_hash = blocks[-1]

    # Create a fork (invalidate the next block after the ancestor and mine 4 blocks on top)
    fork(blocks[0], 4)

    # The last common ancestor between the old best and the new best should be the "ancestor"
    last_common_ancestor, dropped_txs = block_processor.find_last_common_ancestor(best_block_hash)
    assert last_common_ancestor == ancestor
    assert len(dropped_txs) == 3


# TESTS WITH BITCOIND UNREACHABLE
# All BlockProcessor methods should work in a blocking and non-blocking way. The former raises a ConnectionRefusedError,
# while the latter hangs until the event is set back.


def test_get_block_bitcoind_crash(block_processor, block_processor_wrong_connection):
    block_id = get_random_value_hex(32)
    run_test_command_bitcoind_crash(lambda: block_processor_wrong_connection.get_block(block_id))
    run_test_blocking_command_bitcoind_crash(
        block_processor.bitcoind_reachable, lambda: block_processor.get_block(block_id, blocking=True)
    )


def test_get_best_block_hash_bitcoind_crash(block_processor, block_processor_wrong_connection):
    run_test_command_bitcoind_crash(lambda: block_processor_wrong_connection.get_best_block_hash())
    run_test_blocking_command_bitcoind_crash(
        block_processor.bitcoind_reachable, lambda: block_processor.get_best_block_hash(blocking=True)
    )


def test_get_block_count_bitcoind_crash(block_processor, block_processor_wrong_connection):
    run_test_command_bitcoind_crash(lambda: block_processor_wrong_connection.get_block_count())
    run_test_blocking_command_bitcoind_crash(
        block_processor.bitcoind_reachable, lambda: block_processor.get_block_count(blocking=True)
    )


def test_decode_raw_transaction_bitcoind_crash(block_processor, block_processor_wrong_connection):
    run_test_command_bitcoind_crash(lambda: block_processor_wrong_connection.decode_raw_transaction(hex_tx))
    run_test_blocking_command_bitcoind_crash(
        block_processor.bitcoind_reachable, lambda: block_processor.decode_raw_transaction(hex_tx, blocking=True)
    )


def test_get_distance_to_tip_bitcoind_crash(block_processor, block_processor_wrong_connection):
    run_test_command_bitcoind_crash(
        lambda: block_processor_wrong_connection.get_distance_to_tip(get_random_value_hex(32))
    )
    run_test_blocking_command_bitcoind_crash(
        block_processor.bitcoind_reachable,
        lambda: block_processor.get_distance_to_tip(get_random_value_hex(32), blocking=True),
    )


def test_get_missed_blocks_bitcoind_crash(block_processor, block_processor_wrong_connection):
    run_test_command_bitcoind_crash(
        lambda: block_processor_wrong_connection.get_missed_blocks(get_random_value_hex(32))
    )
    run_test_blocking_command_bitcoind_crash(
        block_processor.bitcoind_reachable,
        lambda: block_processor.get_missed_blocks(get_random_value_hex(32), blocking=True),
    )


def test_is_block_in_best_chain_bitcoind_crash(block_processor, block_processor_wrong_connection):
    run_test_command_bitcoind_crash(
        lambda: block_processor_wrong_connection.is_block_in_best_chain(get_random_value_hex(32))
    )

    best_block_hash = block_processor.get_best_block_hash()
    run_test_blocking_command_bitcoind_crash(
        block_processor.bitcoind_reachable,
        lambda: block_processor.is_block_in_best_chain(best_block_hash, blocking=True),
    )


def test_find_last_common_ancestor_bitcoind_crash(block_processor, block_processor_wrong_connection):
    run_test_command_bitcoind_crash(
        lambda: block_processor_wrong_connection.find_last_common_ancestor(get_random_value_hex(32))
    )

    best_block_hash = block_processor.get_best_block_hash()
    run_test_blocking_command_bitcoind_crash(
        block_processor.bitcoind_reachable,
        lambda: block_processor.find_last_common_ancestor(best_block_hash, blocking=True),
    )
