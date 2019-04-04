import zmq
import binascii
from queue import Queue
from threading import Thread
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT, FEED_PROTOCOL, FEED_ADDR, FEED_PORT


class ZMQHandler:
    """ Adapted from https://github.com/bitcoin/bitcoin/blob/master/contrib/zmq/zmq_sub.py"""
    def __init__(self):
        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt(zmq.RCVHWM, 0)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashblock")
        self.zmqSubSocket.connect("%s://%s:%s" % (FEED_PROTOCOL, FEED_ADDR, FEED_PORT))

    def handle(self, debug, block_queue):
        msg = self.zmqSubSocket.recv_multipart()
        topic = msg[0]
        body = msg[1]

        if topic == b"hashblock":
            block_hash = binascii.hexlify(body).decode('UTF-8')
            block_queue.put(block_hash)

            if debug:
                print("New block received from Core ", block_hash)


class Watcher:
    def __init__(self, debug):
        self.appointments = []
        self.sleep = True
        self.debug = debug
        self.block_queue = Queue()

    def add_appointment(self, appointment):
        # ToDo: Discuss about validation of input data
        self.appointments.append(appointment)

        if self.sleep:
            self.sleep = False
            zmq_subscriber = Thread(target=self.do_subscribe, args=[self.block_queue])
            zmq_subscriber.start()
            self.do_watch()

        # Rationale:
        # The Watcher will analyze every received block looking for appointment matches. If there is no work
        # to do the watcher can sleep (appointments = [] and sleep = True) otherwise for every received block
        # the watcher will get the list of transactions and compare it with the list of appointments

    def do_subscribe(self, block_queue):
        daemon = ZMQHandler()
        daemon.handle(self.debug, block_queue)

    def do_watch(self):
        bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                               BTC_RPC_PORT))

        while len(self.appointments) > 0:
            block_hash = self.block_queue.get()

            try:
                block = bitcoin_cli.getblock(block_hash)

                prev_block_id = block.get('previousblockhash')
                txs = block.get('tx')

                # ToDo: Check for every tx in txs if there is an appointment that matches (MS 16-bytes)

                if self.debug:
                    print("New block received ", block_hash)
                    print("Prev. block hash ", prev_block_id)
                    print("List of transactions", txs)

            except JSONRPCException as e:
                print(e)

