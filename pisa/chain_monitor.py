import zmq
import binascii
from threading import Thread, Event, Condition

from common.logger import Logger
from pisa.conf import FEED_PROTOCOL, FEED_ADDR, FEED_PORT
from pisa.block_processor import BlockProcessor

logger = Logger("ChainMonitor")


class ChainMonitor:
    def __init__(self):
        self.best_tip = None
        self.last_tips = []
        self.terminate = False

        self.check_tip = Event()
        self.lock = Condition()

        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt(zmq.RCVHWM, 0)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashblock")
        self.zmqSubSocket.connect("%s://%s:%s" % (FEED_PROTOCOL, FEED_ADDR, FEED_PORT))

        self.watcher_queue = None
        self.responder_queue = None
        self.watcher_asleep = True
        self.responder_asleep = True

    def attach_watcher(self, queue, awake):
        self.watcher_queue = queue
        self.watcher_asleep = awake

    def attach_responder(self, queue, awake):
        self.responder_queue = queue
        self.responder_asleep = awake

    def notify_subscribers(self, block_hash):
        if not self.watcher_asleep:
            self.watcher_queue.put(block_hash)

        if not self.responder_asleep:
            self.responder_queue.put(block_hash)

    def update_state(self, block_hash):
        self.best_tip = block_hash
        self.last_tips.append(block_hash)

        if len(self.last_tips) > 10:
            self.last_tips.pop(0)

    def monitor_chain(self):
        self.best_tip = BlockProcessor.get_best_block_hash()
        Thread(target=self.monitor_chain_polling).start()
        Thread(target=self.monitor_chain_zmq).start()

    def monitor_chain_polling(self):
        while self.terminate:
            self.check_tip.wait(timeout=60)

            # Terminate could have been set wile the thread was blocked in wait
            if not self.terminate:
                current_tip = BlockProcessor.get_best_block_hash()

                self.lock.acquire()
                if current_tip != self.best_tip:
                    self.update_state(current_tip)
                    self.notify_subscribers(current_tip)
                    logger.info("New block received via polling", block_hash=current_tip)
                self.lock.release()

    def monitor_chain_zmq(self):
        while not self.terminate:
            msg = self.zmqSubSocket.recv_multipart()

            # Terminate could have been set wile the thread was blocked in recv
            if not self.terminate:
                topic = msg[0]
                body = msg[1]

                if topic == b"hashblock":
                    block_hash = binascii.hexlify(body).decode("utf-8")

                    self.lock.acquire()
                    if block_hash != self.best_tip and block_hash not in self.last_tips:
                        self.update_state(block_hash)
                        self.notify_subscribers(block_hash)
                        logger.info("New block received via zmq", block_hash=block_hash)
                    self.lock.release()
