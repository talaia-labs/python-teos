import zmq
import time
from queue import Queue
from threading import Thread, Event, Condition
import pytest

from teos.chain_monitor import ChainMonitor, ChainMonitorStatus

from test.teos.conftest import generate_blocks
from test.teos.unit.conftest import get_random_value_hex, bitcoind_feed_params


def test_init(block_processor):
    # run_bitcoind is started here instead of later on to avoid race conditions while it initializes

    # Not much to test here, just sanity checks to make sure nothing goes south in the future
    chain_monitor = ChainMonitor([Queue(), Queue()], block_processor, bitcoind_feed_params)

    assert chain_monitor.status == ChainMonitorStatus.IDLE
    assert isinstance(chain_monitor.last_tips, list) and len(chain_monitor.last_tips) == 0
    assert chain_monitor.status == ChainMonitorStatus.IDLE
    assert isinstance(chain_monitor.check_tip, Event)
    assert isinstance(chain_monitor.lock, Condition)
    assert isinstance(chain_monitor.zmqSubSocket, zmq.Socket)

    assert isinstance(chain_monitor.receiving_queues[0], Queue)
    assert isinstance(chain_monitor.receiving_queues[1], Queue)


def test_notify_subscribers(block_processor):
    queue1 = Queue()
    queue2 = Queue()
    chain_monitor = ChainMonitor([queue1, queue2], block_processor, bitcoind_feed_params)

    # Queues should be empty to start with
    assert queue1.qsize() == 0
    assert queue2.qsize() == 0

    block1 = get_random_value_hex(32)
    block2 = get_random_value_hex(32)
    block3 = get_random_value_hex(32)

    # we add two elements to the internal queue before the thread is started
    chain_monitor.queue.put(block1)
    chain_monitor.queue.put(block2)

    assert queue1.qsize() == 0
    assert queue2.qsize() == 0

    notifying_thread = Thread(target=chain_monitor.notify_subscribers, daemon=True)
    notifying_thread.start()

    # the existing elements should be processed soon and in order for all queues
    for q in [queue1, queue2]:
        assert q.get(timeout=0.1) == block1
        assert q.get(timeout=0.1) == block2

    # Subscribers are only notified as long as they are awake
    chain_monitor.queue.put(block3)

    assert queue1.get(timeout=0.1) == block3
    assert queue2.get(timeout=0.1) == block3

    chain_monitor.terminate()


def test_enqueue(block_processor):
    # The state is updated after receiving a new block (and only if the block is not already known).
    # Let's start by adding some hashes to last_tips
    chain_monitor = ChainMonitor([Queue(), Queue()], block_processor, bitcoind_feed_params)
    chain_monitor.last_tips = [get_random_value_hex(32) for _ in range(5)]

    # Now we can try to update the state with an hash already seen and see how it doesn't work
    assert chain_monitor.enqueue(chain_monitor.last_tips[0]) is False

    # The state should be correctly updated with a new block hash, which should be added as last element of last_tips
    another_block_hash = get_random_value_hex(32)
    assert chain_monitor.enqueue(another_block_hash) is True
    assert chain_monitor.last_tips[-1] == another_block_hash


def test_monitor_chain_polling(block_processor):
    chain_monitor = ChainMonitor([Queue(), Queue()], block_processor, bitcoind_feed_params)
    chain_monitor.last_tips = [block_processor.get_best_block_hash()]
    chain_monitor.polling_delta = 0.1

    # monitor_chain_polling runs until not terminated
    polling_thread = Thread(target=chain_monitor.monitor_chain_polling, daemon=True)
    polling_thread.start()

    # Check that nothing changes as long as a block is not generated
    for _ in range(5):
        assert chain_monitor.queue.empty()
        time.sleep(0.1)

    # And that it does if we generate a block
    generate_blocks(1)

    chain_monitor.queue.get()
    assert chain_monitor.queue.empty()

    chain_monitor.terminate()


def test_monitor_chain_zmq(block_processor):
    responder_queue = Queue()
    chain_monitor = ChainMonitor([Queue(), responder_queue], block_processor, bitcoind_feed_params)
    chain_monitor.last_tips = [block_processor.get_best_block_hash()]

    zmq_thread = Thread(target=chain_monitor.monitor_chain_zmq, daemon=True)
    zmq_thread.start()

    # the internal queue should start empty
    assert chain_monitor.queue.empty()

    # And have a new block every time we generate one
    for _ in range(3):
        generate_blocks(1)

        chain_monitor.queue.get()
        assert chain_monitor.queue.empty()

    chain_monitor.terminate()
    # The zmq thread needs a block generation to release from the recv method.
    generate_blocks(1)


def test_monitor_chain(block_processor):
    # We don't activate it but we start listening; therefore received blocks should accumulate in the internal queue
    chain_monitor = ChainMonitor([Queue(), Queue()], block_processor, bitcoind_feed_params)
    chain_monitor.polling_delta = 0.1

    chain_monitor.monitor_chain()
    assert chain_monitor.status == ChainMonitorStatus.LISTENING

    # The tip is updated before starting the threads, so it should have been added to last_tips.
    assert len(chain_monitor.last_tips) > 0

    # Blocks should be received and added to the queue
    count = 0
    for _ in range(5):
        generate_blocks(1)
        count += 1
        time.sleep(0.5)  # higher than the polling interval
        print(f"Best block: {block_processor.get_best_block_hash()}")
        assert chain_monitor.receiving_queues[0].empty()
        assert chain_monitor.receiving_queues[1].empty()
        assert chain_monitor.queue.qsize() == count

    chain_monitor.terminate()
    # The zmq thread needs a block generation to release from the recv method.
    generate_blocks(1)


def test_monitor_chain_wrong_status_raises(block_processor):
    # calling monitor_chain when not idle should raise
    chain_monitor = ChainMonitor([Queue(), Queue()], block_processor, bitcoind_feed_params)

    for status in ChainMonitorStatus:
        if status != ChainMonitorStatus.IDLE:
            chain_monitor.status = status  # mock the status
            with pytest.raises(RuntimeError, match="can only be called in IDLE status"):
                chain_monitor.monitor_chain()


def test_activate(block_processor):
    # Not much to test here, this should launch two threads (one per monitor approach) and finish on terminate
    chain_monitor = ChainMonitor([Queue(), Queue()], block_processor, bitcoind_feed_params)
    chain_monitor.monitor_chain()
    chain_monitor.activate()
    assert chain_monitor.status == ChainMonitorStatus.ACTIVE

    # last_tips is updated before starting the threads, so it not be empty now.
    assert len(chain_monitor.last_tips) > 0

    # Blocks should be received
    for _ in range(5):
        generate_blocks(1)
        watcher_block = chain_monitor.receiving_queues[0].get()
        responder_block = chain_monitor.receiving_queues[1].get()
        assert watcher_block == responder_block
        assert chain_monitor.receiving_queues[0].empty()
        assert chain_monitor.receiving_queues[1].empty()

    chain_monitor.terminate()
    # The zmq thread needs a block generation to release from the recv method.
    generate_blocks(1)


def test_activate_wrong_status_raises(block_processor):
    # calling activate when not listening should raise
    chain_monitor = ChainMonitor([Queue(), Queue()], block_processor, bitcoind_feed_params)

    for status in ChainMonitorStatus:
        if status != ChainMonitorStatus.LISTENING:
            chain_monitor.status = status  # mock the status
            with pytest.raises(RuntimeError, match="can only be called in LISTENING status"):
                chain_monitor.activate()


def test_monitor_chain_single_update(block_processor):
    # This test tests that if both threads try to add the same block to the queue, only the first one will make it
    chain_monitor = ChainMonitor([Queue(), Queue()], block_processor, bitcoind_feed_params)

    chain_monitor.polling_delta = 2

    # We will create a block and wait for the polling thread. Then check the queues to see that the block hash has only
    # been added once.
    chain_monitor.monitor_chain()
    chain_monitor.activate()
    generate_blocks(1)

    assert len(chain_monitor.receiving_queues) == 2

    queue0_block = chain_monitor.receiving_queues[0].get()
    queue1_block = chain_monitor.receiving_queues[1].get()
    assert queue0_block == queue1_block
    assert chain_monitor.receiving_queues[0].empty()
    assert chain_monitor.receiving_queues[1].empty()

    # The delta for polling is 2 secs, so let's wait and see
    time.sleep(2)
    assert chain_monitor.receiving_queues[0].empty()
    assert chain_monitor.receiving_queues[1].empty()

    # We can also force an update and see that it won't go through
    assert chain_monitor.enqueue(queue0_block) is False

    chain_monitor.terminate()
    # The zmq thread needs a block generation to release from the recv method.
    generate_blocks(1)


def test_terminate(block_processor):
    chain_monitor = ChainMonitor([Queue(), Queue()], block_processor, bitcoind_feed_params)

    chain_monitor.terminate()

    assert chain_monitor.status == ChainMonitorStatus.TERMINATED


@pytest.mark.timeout(5)
def test_threads_stop_when_terminated(block_processor):
    # When status is "terminated", the methods running the threads should stop immediately

    chain_monitor = ChainMonitor([Queue(), Queue()], block_processor, bitcoind_feed_params)
    chain_monitor.terminate()

    # If any of the function does not exit immediately, the test will timeout
    chain_monitor.monitor_chain_polling()
    chain_monitor.monitor_chain_zmq()
    chain_monitor.notify_subscribers()
