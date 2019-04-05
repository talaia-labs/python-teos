import zmq
import binascii
from queue import Queue
from threading import Thread
from pisa.tools import decrypt_tx
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT, FEED_PROTOCOL, FEED_ADDR, FEED_PORT, \
    MAX_APPOINTMENTS


class ZMQHandler:
    """ Adapted from https://github.com/bitcoin/bitcoin/blob/master/contrib/zmq/zmq_sub.py"""
    def __init__(self):
        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt(zmq.RCVHWM, 0)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashblock")
        self.zmqSubSocket.connect("%s://%s:%s" % (FEED_PROTOCOL, FEED_ADDR, FEED_PORT))

    def handle(self, block_queue, debug):
        msg = self.zmqSubSocket.recv_multipart()
        topic = msg[0]
        body = msg[1]

        if topic == b"hashblock":
            block_hash = binascii.hexlify(body).decode('UTF-8')
            block_queue.put(block_hash)

            if debug:
                print("New block received from Core ", block_hash)


class Watcher:
    def __init__(self, max_appointments=MAX_APPOINTMENTS):
        self.appointments = dict()
        self.block_queue = Queue()
        self.asleep = True
        self.max_appointments = max_appointments

    def add_appointment(self, appointment, debug):
        # ToDo: Discuss about validation of input data

        # Rationale:
        # The Watcher will analyze every received block looking for appointment matches. If there is no work
        # to do the watcher can sleep (appointments = {} and sleep = True) otherwise for every received block
        # the watcher will get the list of transactions and compare it with the list of appointments.
        # If the watcher is awake, every new appointment will just be added to the appointment list until
        # max_appointments is reached.

        # ToDo: Check how to handle appointment completion

        if len(self.appointments) < self.max_appointments:
            # Appointments are identified by the locator: the most significant 16 bytes of the commitment txid.
            # While 16-byte hash collisions are not likely, they are possible, so we will store appointments in lists
            # even if we only have one (so the code logic is simplified from this point on).
            if not self.appointments.get(appointment.locator):
                self.appointments[appointment.locator] = []

            # Use an internal id (position in the list) to distinguish between different appointments with the same
            # locator
            appointment.id = len(self.appointments[appointment.locator])
            self.appointments[appointment.locator].append(appointment)

            if self.asleep:
                self.asleep = False
                zmq_subscriber = Thread(target=self.do_subscribe, args=[self.block_queue, debug])
                watcher = Thread(target=self.do_watch, args=[debug])
                zmq_subscriber.start()
                watcher.start()

            appointment_added = True

        else:
            appointment_added = False

        return appointment_added

    def do_subscribe(self, block_queue, debug):
        daemon = ZMQHandler()
        daemon.handle(block_queue, debug)

    def do_watch(self, debug):
        bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                               BTC_RPC_PORT))

        while len(self.appointments) > 0:
            block_hash = self.block_queue.get()

            try:
                block = bitcoin_cli.getblock(block_hash)
                prev_block_id = block.get('previousblockhash')
                txs = block.get('tx')

                if debug:
                    print("New block received", block_hash)
                    print("Prev. block hash", prev_block_id)
                    print("List of transactions", txs)

                potential_matches = []

                for k in self.appointments.keys():
                    potential_matches += [(k, tx[32:]) for tx in txs if tx.startswith(k)]

                if debug:
                    if len(potential_matches) > 0:
                        print("List of potential matches", potential_matches)
                    else:
                        print("No potential matches found")

                matches = self.check_potential_matches(potential_matches, bitcoin_cli)

                # ToDo: Handle matches
                # ToDo: Matches will be empty list if no matches, list of matches otherwise
                # ToDo: Notify responder with every match.
                # ToDo: Get rid of appointment? Set appointment to a different state (create appointment state first)?

            except JSONRPCException as e:
                print(e)
                continue

    def check_potential_matches(self, potential_matches, bitcoin_cli):
        matches = []

        for locator, k in potential_matches:
            for appointment in self.appointments.get(locator):
                try:
                    decrypted_data = decrypt_tx(appointment.encrypted_blob, k, appointment.cypher)
                    bitcoin_cli.decoderawtransaction(decrypted_data)
                    matches.append((locator, appointment.id, decrypted_data))
                except JSONRPCException as e:
                    # Tx decode failed returns error code -22, maybe we should be more strict here. Leaving it simple
                    # for the POC
                    print(e)
                    continue

        return matches


