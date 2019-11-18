import pytest

from pisa import c_logger
from pisa.block_processor import BlockProcessor
from pisa.utils.auth_proxy import JSONRPCException
from test.unit.conftest import get_random_value_hex

c_logger.disabled = True


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
    hex_tx = (
        "0100000001c997a5e56e104102fa209c6a852dd90660a20b2d9c352423edce25857fcd3704000000004847304402"
        "204e45e16932b8af514961a1d3a1a25fdf3f4f7732e9d624c6c61548ab5fb8cd410220181522ec8eca07de4860a4"
        "acdd12909d831cc56cbbac4622082221a8768d1d0901ffffffff0200ca9a3b00000000434104ae1a62fe09c5f51b"
        "13905f07f06b99a2f7159b2225f374cd378d71302fa28414e7aab37397f554a7df5f142c21c1b7303b8a0626f1ba"
        "ded5c72a704f7e6cd84cac00286bee0000000043410411db93e1dcdb8a016b49840f8c53bc1eb68a382e97b1482e"
        "cad7b148a6909a5cb2e0eaddfb84ccf9744464f82e160bfa9b8b64f9d4c03f999b8643f656b412a3ac00000000"
    )

    try:
        BlockProcessor.decode_raw_transaction(hex_tx)
        assert True
    except JSONRPCException:
        assert False


def test_decode_raw_transaction_invalid():
    # Same but with an invalid one

    hex_tx = "A" * 16

    try:
        BlockProcessor.decode_raw_transaction(hex_tx)
        assert False
    except JSONRPCException:
        assert True
