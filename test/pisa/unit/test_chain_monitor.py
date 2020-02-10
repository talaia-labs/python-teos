import zmq
import time
from queue import Queue
from threading import Thread, Event, Condition

from pisa.block_processor import BlockProcessor
from pisa.chain_monitor import ChainMonitor

from test.pisa.unit.conftest import get_random_value_hex, generate_block


def test_init(run_bitcoind):
    # run_bitcoind is started here instead of later on to avoid race conditions while it initializes

    # Not much to test here, just sanity checks to make sure nothing goes south in the future
    chain_monitor = ChainMonitor(Queue(), Queue())

    assert chain_monitor.best_tip is None
    assert isinstance(chain_monitor.last_tips, list) and len(chain_monitor.last_tips) == 0
    assert chain_monitor.terminate is False
    assert isinstance(chain_monitor.check_tip, Event)
    assert isinstance(chain_monitor.lock, Condition)
    assert isinstance(chain_monitor.zmqSubSocket, zmq.Socket)

    # The Queues and asleep flags are initialized when attaching the corresponding subscriber
    assert isinstance(chain_monitor.watcher_queue, Queue)
    assert isinstance(chain_monitor.responder_queue, Queue)


def test_notify_subscribers():
    chain_monitor = ChainMonitor(Queue(), Queue())
    # Subscribers are only notified as long as they are awake
    new_block = get_random_value_hex(32)

    # Queues should be empty to start with
    assert chain_monitor.watcher_queue.empty()
    assert chain_monitor.responder_queue.empty()

    chain_monitor.notify_subscribers(new_block)

    assert chain_monitor.watcher_queue.get() == new_block
    assert chain_monitor.responder_queue.get() == new_block


def test_update_state():
    # The state is updated after receiving a new block (and only if the block is not already known).
    # Let's start by setting a best_tip and a couple of old tips
    new_block_hash = get_random_value_hex(32)
    chain_monitor = ChainMonitor(Queue(), Queue())
    chain_monitor.best_tip = new_block_hash
    chain_monitor.last_tips = [get_random_value_hex(32) for _ in range(5)]

    # Now we can try to update the state with an old best_tip and see how it doesn't work
    assert chain_monitor.update_state(chain_monitor.last_tips[0]) is False

    # Same should happen with the current tip
    assert chain_monitor.update_state(chain_monitor.best_tip) is False

    # The state should be correctly updated with a new block hash, the chain tip should change and the old tip should
    # have been added to the last_tips
    another_block_hash = get_random_value_hex(32)
    assert chain_monitor.update_state(another_block_hash) is True
    assert chain_monitor.best_tip == another_block_hash and new_block_hash == chain_monitor.last_tips[-1]


def test_monitor_chain_polling(db_manager):
    # Try polling with the Watcher
    wq = Queue()
    chain_monitor = ChainMonitor(wq, Queue())
    chain_monitor.best_tip = BlockProcessor.get_best_block_hash()

    # monitor_chain_polling runs until terminate if set
    polling_thread = Thread(target=chain_monitor.monitor_chain_polling, kwargs={"polling_delta": 0.1}, daemon=True)
    polling_thread.start()

    # Check that nothing changes as long as a block is not generated
    for _ in range(5):
        assert chain_monitor.watcher_queue.empty()
        time.sleep(0.1)

    # And that it does if we generate a block
    generate_block()

    chain_monitor.watcher_queue.get()
    assert chain_monitor.watcher_queue.empty()

    chain_monitor.terminate = True
    polling_thread.join()


def test_monitor_chain_zmq(db_manager):
    rq = Queue()
    chain_monitor = ChainMonitor(Queue(), rq)
    chain_monitor.best_tip = BlockProcessor.get_best_block_hash()

    zmq_thread = Thread(target=chain_monitor.monitor_chain_zmq, daemon=True)
    zmq_thread.start()

    # Queues should start empty
    assert chain_monitor.responder_queue.empty()

    # And have a new block every time we generate one
    for _ in range(3):
        generate_block()
        chain_monitor.responder_queue.get()
        assert chain_monitor.responder_queue.empty()


def test_monitor_chain(db_manager):
    # Not much to test here, this should launch two threads (one per monitor approach) and finish on terminate
    chain_monitor = ChainMonitor(Queue(), Queue())

    chain_monitor.best_tip = None
    chain_monitor.monitor_chain()

    # The tip is updated before starting the threads, so it should have changed.
    assert chain_monitor.best_tip is not None

    # Blocks should be received
    for _ in range(5):
        generate_block()
        watcher_block = chain_monitor.watcher_queue.get()
        responder_block = chain_monitor.responder_queue.get()
        assert watcher_block == responder_block
        assert chain_monitor.watcher_queue.empty()
        assert chain_monitor.responder_queue.empty()

    # And the thread be terminated on terminate
    chain_monitor.terminate = True
    # The zmq thread needs a block generation to release from the recv method.
    generate_block()


def test_monitor_chain_single_update(db_manager):
    # This test tests that if both threads try to add the same block to the queue, only the first one will make it
    chain_monitor = ChainMonitor(Queue(), Queue())

    chain_monitor.best_tip = None

    # We will create a block and wait for the polling thread. Then check the queues to see that the block hash has only
    # been added once.
    chain_monitor.monitor_chain(polling_delta=2)
    generate_block()

    watcher_block = chain_monitor.watcher_queue.get()
    responder_block = chain_monitor.responder_queue.get()
    assert watcher_block == responder_block
    assert chain_monitor.watcher_queue.empty()
    assert chain_monitor.responder_queue.empty()

    # The delta for polling is 2 secs, so let's wait and see
    time.sleep(2)
    assert chain_monitor.watcher_queue.empty()
    assert chain_monitor.responder_queue.empty()

    # We can also force an update and see that it won't go through
    assert chain_monitor.update_state(watcher_block) is False
