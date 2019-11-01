from queue import Queue
import zmq
import binascii
from pisa.logger import Logger
from pisa.conf import FEED_PROTOCOL, FEED_ADDR, FEED_PORT


# ToDo: #7-add-async-back-to-zmq
class ZMQHandler:
    """ Adapted from https://github.com/bitcoin/bitcoin/blob/master/contrib/zmq/zmq_sub.py"""

    def __init__(self):
        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt(zmq.RCVHWM, 0)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashblock")
        self.zmqSubSocket.connect("%s://%s:%s" % (FEED_PROTOCOL, FEED_ADDR, FEED_PORT))
        self.logger = Logger("ZMQHandler")
        self.terminate = False

        self.watch_block_queue = Queue()
        self.respond_block_queue = Queue()

    def handle(self):
        while not self.terminate:
            msg = self.zmqSubSocket.recv_multipart()

            # Terminate could have been set while the thread was blocked in recv
            if not self.terminate:
                topic = msg[0]
                body = msg[1]

                if topic == b"hashblock":
                    block_hash = binascii.hexlify(body).decode("UTF-8")
                    if not self.watch_asleep:
                        self.watch_block_queue.put(block_hash)
                    if not self.respond_asleep:
                        self.respond_block_queue.put(block_hash)

                    self.logger.info("New block received via ZMQ", block_hash=block_hash)
