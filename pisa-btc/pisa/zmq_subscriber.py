import zmq
import binascii
from conf import FEED_PROTOCOL, FEED_ADDR, FEED_PORT


class ZMQHandler:
    """ Adapted from https://github.com/bitcoin/bitcoin/blob/master/contrib/zmq/zmq_sub.py"""
    def __init__(self):
        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt(zmq.RCVHWM, 0)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashblock")
        self.zmqSubSocket.connect("%s://%s:%s" % (FEED_PROTOCOL, FEED_ADDR, FEED_PORT))

    def handle(self, block_queue, debug, logging):
        while True:
            msg = self.zmqSubSocket.recv_multipart()
            topic = msg[0]
            body = msg[1]

            if topic == b"hashblock":
                block_hash = binascii.hexlify(body).decode('UTF-8')
                block_queue.put(block_hash)

                if debug:
                    logging.info("[ZMQHandler] new block received via ZMQ".format(block_hash))
