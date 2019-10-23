import re
import pytest
from time import sleep
from threading import Thread

from test.simulator.transaction import TX
from test.unit.conftest import get_random_value_hex
from test.simulator.bitcoind_sim import run_simulator
from pisa.utils.auth_proxy import AuthServiceProxy, JSONRPCException
from pisa.conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT

MIXED_VALUES = values = [-1, 500, '', '111', [], 1.1, None, '', "a" * 31, "b" * 33, get_random_value_hex(32)]

bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT))


@pytest.fixture(scope='module')
def run_bitcoind():
    bitcoind_thread = Thread(target=run_simulator, kwargs={"mode": "event"})
    bitcoind_thread.daemon = True
    bitcoind_thread.start()

    # It takes a little bit of time to start the API (otherwise the requests are sent too early and they fail)
    sleep(0.1)


@pytest.fixture(scope="module")
def genesis_block_hash(run_bitcoind):
    return bitcoin_cli.getblockhash(0)


def check_hash_format(txid):
    # TODO: #12-check-txid-regexp
    return isinstance(txid, str) and re.search(r'^[0-9A-Fa-f]{64}$', txid) is not None


def test_help(run_bitcoind):
    # Help should always return 0
    assert(bitcoin_cli.help() == 0)


# FIXME: Better assert for the exceptions would be nice (check the returned errno is the expected one)

def test_getblockhash(genesis_block_hash):
    # First block
    assert(check_hash_format(genesis_block_hash))

    # Check that the values are within range and of the proper format (all should fail)
    for v in MIXED_VALUES:
        try:
            bitcoin_cli.getblockhash(v)
            assert False
        except JSONRPCException as e:
            assert True


def test_get_block(genesis_block_hash):
    # getblock should return a list of transactions and the height
    block = bitcoin_cli.getblock(genesis_block_hash)
    assert(isinstance(block.get('tx'), list))
    assert(len(block.get('tx')) != 0)
    assert(isinstance(block.get('height'), int))

    # It should fail for wrong data formats and random ids
    for v in MIXED_VALUES:
        try:
            bitcoin_cli.getblock(v)
            assert False
        except JSONRPCException as e:
            assert True


def test_decoderawtransaction(genesis_block_hash):
    # decoderawtransaction should only return if the given transaction matches a txid format
    block = bitcoin_cli.getblock(genesis_block_hash)
    coinbase_txid = block.get('tx')[0]

    coinbase_tx = bitcoin_cli.getrawtransaction(coinbase_txid).get("hex")
    tx = bitcoin_cli.decoderawtransaction(coinbase_tx)

    assert(isinstance(tx, dict))
    assert(isinstance(tx.get('txid'), str))
    assert(check_hash_format(tx.get('txid')))

    # Therefore should also work for a random transaction hex in our simulation
    random_tx = TX.create_dummy_transaction()
    tx = bitcoin_cli.decoderawtransaction(random_tx)
    assert(isinstance(tx, dict))
    assert(isinstance(tx.get('txid'), str))
    assert(check_hash_format(tx.get('txid')))

    # But it should fail for not proper formatted one
    for v in MIXED_VALUES:
        try:
            bitcoin_cli.decoderawtransaction(v)
            assert False
        except JSONRPCException as e:
            assert True


def test_sendrawtransaction(genesis_block_hash):
    # sendrawtransaction should only allow txids that the simulator has not mined yet
    bitcoin_cli.sendrawtransaction(TX.create_dummy_transaction())

    # Any data not matching the txid format or that matches with an already mined transaction should fail
    try:
        genesis_tx = bitcoin_cli.getblock(genesis_block_hash).get("tx")[0]
        bitcoin_cli.sendrawtransaction(genesis_tx)
        assert False

    except JSONRPCException as e:
        assert True

    for v in MIXED_VALUES:
        try:
            bitcoin_cli.sendrawtransaction(v)
            assert False
        except JSONRPCException as e:
            assert True


def test_getrawtransaction(genesis_block_hash):
    # getrawtransaction should work for existing transactions, and fail for non-existing ones
    genesis_tx = bitcoin_cli.getblock(genesis_block_hash).get("tx")[0]
    tx = bitcoin_cli.getrawtransaction(genesis_tx)

    assert(isinstance(tx, dict))
    assert(isinstance(tx.get('confirmations'), int))

    for v in MIXED_VALUES:
        try:
            bitcoin_cli.getrawtransaction(v)
            assert False
        except JSONRPCException as e:
            assert True


def test_getblockcount():
    # getblockcount should always return a positive integer
    bc = bitcoin_cli.getblockcount()
    assert (isinstance(bc, int))
    assert (bc >= 0)




