"""
Adapted from https://github.com/bitcoin/bitcoin/blob/master/contrib/zmq/zmq_sub.py
"""

import binascii
import zmq
import conf
from pisa import shared


class ZMQHandler:
    def __init__(self):
        self.zmqContext = zmq.Context()

        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt(zmq.RCVHWM, 0)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashblock")

        self.zmqSubSocket.connect("%s://%s:%s" % (conf.FEED_PROTOCOL, conf.FEED_ADDR, conf.FEED_PORT))

    def handle(self, debug):
        msg = self.zmqSubSocket.recv_multipart()
        topic = msg[0]
        body = msg[1]

        if topic == b"hashblock":
            block_hash = binascii.hexlify(body).decode('UTF-8')
            shared.block_queue.put(block_hash)

            if debug:
                # Log shit
                pass


def run_subscribe(debug):
    daemon = ZMQHandler()
    daemon.handle(debug)
