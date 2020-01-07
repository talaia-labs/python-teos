import zmq
import time
from threading import Thread, Event, Condition

from pisa.watcher import Watcher
from pisa.responder import Responder
from pisa.block_processor import BlockProcessor
from pisa.chain_monitor import ChainMonitor

from test.pisa.unit.conftest import get_random_value_hex, generate_block


def test_init(run_bitcoind):
    # run_bitcoind is started here instead of later on to avoid race conditions while it initializes

    # Not much to test here, just sanity checks to make sure nothings goes south in the future
    chain_monitor = ChainMonitor()

    assert chain_monitor.best_tip is None
    assert isinstance(chain_monitor.last_tips, list) and len(chain_monitor.last_tips) == 0
    assert chain_monitor.terminate is False
    assert isinstance(chain_monitor.check_tip, Event)
    assert isinstance(chain_monitor.lock, Condition)
    assert isinstance(chain_monitor.zmqSubSocket, zmq.Socket)

    # The Queues and asleep flags are initialized when attaching the corresponding subscriber
    assert chain_monitor.watcher_queue is None
    assert chain_monitor.responder_queue is None
    assert chain_monitor.watcher_asleep and chain_monitor.responder_asleep


def test_attach_watcher(chain_monitor):
    watcher = Watcher(db_manager=None, chain_monitor=chain_monitor, sk_der=None)
    chain_monitor.attach_watcher(watcher.block_queue, watcher.asleep)

    # booleans are not passed as reference in Python, so the flags need to be set separately
    assert watcher.asleep == chain_monitor.watcher_asleep
    watcher.asleep = False
    assert chain_monitor.watcher_asleep != watcher.asleep

    # Test that the Queue work
    r_hash = get_random_value_hex(32)
    chain_monitor.watcher_queue.put(r_hash)
    assert watcher.block_queue.get() == r_hash


def test_attach_responder(chain_monitor):
    responder = Responder(db_manager=None, chain_monitor=chain_monitor)
    chain_monitor.attach_responder(responder.block_queue, responder.asleep)

    # Same kind of testing as with the attach watcher
    assert responder.asleep == chain_monitor.watcher_asleep
    responder.asleep = False
    assert chain_monitor.watcher_asleep != responder.asleep

    r_hash = get_random_value_hex(32)
    chain_monitor.responder_queue.put(r_hash)
    assert responder.block_queue.get() == r_hash


def test_notify_subscribers(chain_monitor):
    # Subscribers are only notified as long as they are awake
    new_block = get_random_value_hex(32)

    # Queues should be empty to start with
    assert chain_monitor.watcher_queue.empty()
    assert chain_monitor.responder_queue.empty()

    chain_monitor.watcher_asleep = True
    chain_monitor.responder_asleep = True
    chain_monitor.notify_subscribers(new_block)

    # And remain empty afterwards since both subscribers where asleep
    assert chain_monitor.watcher_queue.empty()
    assert chain_monitor.responder_queue.empty()

    # Let's flag them as awake and try again
    chain_monitor.watcher_asleep = False
    chain_monitor.responder_asleep = False
    chain_monitor.notify_subscribers(new_block)

    assert chain_monitor.watcher_queue.get() == new_block
    assert chain_monitor.responder_queue.get() == new_block


def test_update_state(chain_monitor):
    # The state is updated after receiving a new block (and only if the block is not already known).
    # Let's start by setting a best_tip and a couple of old tips
    new_block_hash = get_random_value_hex(32)
    chain_monitor.best_tip = new_block_hash
    chain_monitor.last_tips = [get_random_value_hex(32) for _ in range(5)]

    # Now we can try to update the state with an old best_tip and see how it doesn't work
    assert chain_monitor.update_state(chain_monitor.last_tips[0]) is False

    # Same should happen with the current tip
    assert chain_monitor.update_state(chain_monitor.best_tip) is False

    # The state should be correctly updated with a new block hash, the chain tip should change and the old tip should
    # has been added to the last_tips
    another_block_hash = get_random_value_hex(32)
    assert chain_monitor.update_state(another_block_hash) is True
    assert chain_monitor.best_tip == another_block_hash and new_block_hash == chain_monitor.last_tips[-1]


def test_monitor_chain_polling():
    # Try polling with the Watcher
    chain_monitor = ChainMonitor()
    chain_monitor.best_tip = BlockProcessor.get_best_block_hash()

    watcher = Watcher(db_manager=None, chain_monitor=chain_monitor, sk_der=None)
    chain_monitor.attach_watcher(watcher.block_queue, asleep=False)

    # monitor_chain_polling runs until terminate if set
    polling_thread = Thread(target=chain_monitor.monitor_chain_polling, kwargs={"polling_delta": 0.1}, daemon=True)
    polling_thread.start()

    # Check that nothings changes as long as a block is not generated
    for _ in range(5):
        assert chain_monitor.watcher_queue.empty()
        time.sleep(0.1)

    # And that it does if we generate a block
    generate_block()

    chain_monitor.watcher_queue.get()
    assert chain_monitor.watcher_queue.empty()

    chain_monitor.terminate = True
    polling_thread.join()


def test_monitor_chain_zmq():
    # Try zmq with the Responder
    chain_monitor = ChainMonitor()
    chain_monitor.best_tip = BlockProcessor.get_best_block_hash()

    responder = Responder(db_manager=None, chain_monitor=chain_monitor)
    chain_monitor.attach_responder(responder.block_queue, asleep=False)

    zmq_thread = Thread(target=chain_monitor.monitor_chain_zmq, daemon=True)
    zmq_thread.start()

    # Queues should start empty
    assert chain_monitor.responder_queue.empty()

    # And have a new block every time we generate one
    for _ in range(3):
        generate_block()
        chain_monitor.responder_queue.get()
        assert chain_monitor.responder_queue.empty()

    # If we flag it to sleep no notification is sent
    chain_monitor.responder_asleep = True

    for _ in range(3):
        generate_block()
        assert chain_monitor.responder_queue.empty()

    chain_monitor.terminate = True
    # The zmq thread needs a block generation to release from the recv method.
    generate_block()

    zmq_thread.join()


def test_monitor_chain():
    # Not much to test here, this should launch two threads (one per monitor approach) and finish on terminate
    chain_monitor = ChainMonitor()

    watcher = Watcher(db_manager=None, chain_monitor=chain_monitor, sk_der=None)
    responder = Responder(db_manager=None, chain_monitor=chain_monitor)
    chain_monitor.attach_responder(responder.block_queue, asleep=False)
    chain_monitor.attach_watcher(watcher.block_queue, asleep=False)

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
