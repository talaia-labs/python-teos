from time import sleep
from copy import deepcopy
from threading import Thread, Event

from teos.teosd import get_config
from teos.chain_monitor import ChainMonitor
from teos.block_processor import BlockProcessor

cmd_args = {"BTC_NETWORK": "regtest"}
config = get_config(cmd_args, ".teos")


def test_bitcoind_crash_concurrency(run_bitcoind):
    wrong_config = deepcopy(config)
    wrong_config["BTC_RPC_PORT"] = 1234

    # Shared lock
    bitcoind_reachable = Event()
    bitcoind_reachable.set()

    # Setup BlockProcessor and ChainMonitor
    block_processor = BlockProcessor(config, bitcoind_reachable)
    chain_monitor = ChainMonitor([], block_processor, config)
    chain_monitor.polling_delta = 1
    chain_monitor.monitor_chain()
    chain_monitor.activate()

    # Make the connection with bitcoin fail
    block_processor.btc_connect_params = wrong_config

    # Request some data with BlockProcessor so the lock is cleared.
    t = Thread(target=block_processor.get_best_block_hash, kwargs={"blocking": True}, daemon=True)
    t.start()
    # Sleep main thread to ensure the child runs.
    sleep(1)

    # The lock should now be cleared
    assert not bitcoind_reachable.is_set()

    # The polling delta has been changed to 1 sec, so setting back the right connection details and wait for a few
    # seconds should release the lock
    block_processor.btc_connect_params = config
    sleep(5)

    assert bitcoind_reachable.is_set()
    # The child thread should have finished too
    assert not t.is_alive()
