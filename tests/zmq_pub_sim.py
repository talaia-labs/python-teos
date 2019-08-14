import zmq
import time
from binascii import unhexlify
from pisa.conf import FEED_PROTOCOL, FEED_ADDR, FEED_PORT


class ZMQServerSimulator:
    def __init__(self, topic=b'hashblock'):
        self.topic = topic
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind("%s://%s:%s" % (FEED_PROTOCOL, FEED_ADDR, FEED_PORT))

    def mine_block(self, block_hash):
        self.socket.send_multipart([self.topic, block_hash])
        time.sleep(1)


if __name__ == '__main__':
    simulator = ZMQServerSimulator()

    block_hash = unhexlify('0000000000000000000873e8ebc0bb1e61e560a773ec2319457b71f1b4030be0')

    while True:
        simulator.mine_block(block_hash)
