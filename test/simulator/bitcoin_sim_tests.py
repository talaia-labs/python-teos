import os
import binascii
from pisa.utils.authproxy import AuthServiceProxy, JSONRPCException
from pisa.conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT
from pisa.tools import check_txid_format


bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT))

# Help should always return 0
assert(bitcoin_cli.help() == 0)

# getblockhash should return a blockid (which matches the txid format)
block_hash = bitcoin_cli.getblockhash(0)
assert(check_txid_format(block_hash))

# Check that the values are within range and of the proper format (all should fail)
values = [-1, 500, None, '', '111', [], 1.1]
print("getblockhash fails ({}):".format(len(values)))

for v in values:
    try:
        block_hash = bitcoin_cli.getblockhash(v)
        assert False
    except JSONRPCException as e:
        print('\t{}'.format(e))

# getblock should return a list of transactions and the height
block = bitcoin_cli.getblock(block_hash)
assert(isinstance(block.get('tx'), list))
assert(len(block.get('tx')) != 0)
assert(isinstance(block.get('height'), int))

# Some fails
values += ["a"*64, binascii.hexlify(os.urandom(32)).decode()]
print("\ngetblock fails ({}):".format(len(values)))

for v in values:
    try:
        block = bitcoin_cli.getblock(v)
        assert False
    except JSONRPCException as e:
        print('\t{}'.format(e))

# decoderawtransaction should only return if the given transaction matches a txid format
coinbase_tx = block.get('tx')[0]
tx = bitcoin_cli.decoderawtransaction(coinbase_tx)
assert(isinstance(tx, dict))
assert(isinstance(tx.get('txid'), str))
assert(check_txid_format(tx.get('txid')))

# Therefore should also work for a random formatted 32-byte hex in our simulation
random_tx = binascii.hexlify(os.urandom(32)).decode()
tx = bitcoin_cli.decoderawtransaction(random_tx)
assert(isinstance(tx, dict))
assert(isinstance(tx.get('txid'), str))
assert(check_txid_format(tx.get('txid')))

# But it should fail for not proper formatted one
values = [1, None, '', "a"*63, "b"*65, [], binascii.hexlify(os.urandom(31)).hex()]
print("\ndecoderawtransaction fails ({}):".format(len(values)))

for v in values:
    try:
        block = bitcoin_cli.decoderawtransaction(v)
        assert False
    except JSONRPCException as e:
        print('\t{}'.format(e))

# sendrawtransaction should only allow txids that the simulator has not mined yet
bitcoin_cli.sendrawtransaction(binascii.hexlify(os.urandom(32)).decode())

# Any data not matching the txid format or that matches with an already mined transaction should fail
values += [coinbase_tx]

print("\nsendrawtransaction fails ({}):".format(len(values)))

for v in values:
    try:
        block = bitcoin_cli.sendrawtransaction(v)
        assert False
    except JSONRPCException as e:
        print('\t{}'.format(e))

# getrawtransaction should work for existing transactions, and fail for non-existing ones
tx = bitcoin_cli.getrawtransaction(coinbase_tx)

assert(isinstance(tx, dict))
assert(isinstance(tx.get('confirmations'), int))

print("\nsendrawtransaction fails ({}):".format(len(values)))

for v in values:
    try:
        block = bitcoin_cli.sendrawtransaction(v)
        assert False
    except JSONRPCException as e:
        print('\t{}'.format(e))

# getblockcount should always return a positive integer
bc = bitcoin_cli.getblockcount()
assert (isinstance(bc, int))
assert (bc >= 0)

print("\nAll tests passed!")




