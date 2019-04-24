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

    def handle(self, block_queue, debug, logging):
        msg = self.zmqSubSocket.recv_multipart()
        topic = msg[0]
        body = msg[1]

        if topic == b"hashblock":
            block_hash = binascii.hexlify(body).decode('UTF-8')
            block_queue.put(block_hash)

            if debug:
                logging.info("[ZMQHandler] new block received via ZMQ".format(block_hash))


class Watcher:
    def __init__(self, max_appointments=MAX_APPOINTMENTS):
        self.appointments = dict()
        self.block_queue = Queue()
        self.asleep = True
        self.max_appointments = max_appointments

    def add_appointment(self, appointment, debug, logging):
        # ToDo: Discuss about validation of input data

        # Rationale:
        # The Watcher will analyze every received block looking for appointment matches. If there is no work
        # to do the watcher can go sleep (if appointments = {} then asleep = True) otherwise for every received block
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

            self.appointments[appointment.locator].append(appointment)

            if self.asleep:
                self.asleep = False
                zmq_subscriber = Thread(target=self.do_subscribe, args=[self.block_queue, debug, logging])
                watcher = Thread(target=self.do_watch, args=[debug, logging])
                zmq_subscriber.start()
                watcher.start()

            appointment_added = True

            if debug:
                logging.info('[Watcher] new appointment accepted (locator = {})'.format(appointment.locator))

        else:
            appointment_added = False

            if debug:
                logging.info('[Watcher] maximum appointments reached, appointment rejected (locator = {}).'
                             .format(appointment.locator))

        return appointment_added

    def do_subscribe(self, block_queue, debug, logging):
        daemon = ZMQHandler()
        daemon.handle(block_queue, debug, logging)

    def do_watch(self, debug, logging):
        bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                               BTC_RPC_PORT))

        while len(self.appointments) > 0:
            block_hash = self.block_queue.get()

            try:
                block = bitcoin_cli.getblock(block_hash)
                # ToDo: prev_block_id will be used  to store chain state and handle reorgs
                prev_block_id = block.get('previousblockhash')
                txs = block.get('tx')

                if debug:
                    logging.info("[Watcher] new block received {}".format(block_hash))
                    logging.info("[Watcher] prev. block hash {}".format(prev_block_id))
                    logging.info("[Watcher] list of transactions: {}".format(txs))

                potential_matches = []

                for locator in self.appointments.keys():
                    potential_matches += [(locator, tx[32:]) for tx in txs if tx.startswith(locator)]

                if debug:
                    if len(potential_matches) > 0:
                        logging.info("[Watcher] list of potential matches: {}".format(potential_matches))
                    else:
                        logging.info("[Watcher] no potential matches found")

                matches = self.check_potential_matches(potential_matches, bitcoin_cli, debug, logging)

                for locator, appointment_pos, transaction in matches:
                    # ToDo: Notify responder with every match.
                    # notify_responder(transaction)

                    # If there was only one appointment that matches the locator we can delete the whole list
                    # ToDo: We may want to use locks before adding / removing appointment
                    if len(self.appointments[locator]) == 1:
                        del self.appointments[locator]
                    else:
                        # Otherwise we just delete the appointment that matches locator:appointment_pos
                        del self.appointments[locator][appointment_pos]

                    if debug:
                        logging.error("[Watcher] Notifying responder about {}:{} and deleting appointment"
                                      .format(locator, appointment_pos))
            except JSONRPCException as e:
                logging.error("[Watcher] JSONRPCException. Error code {}".format(e))
                continue

    def check_potential_matches(self, potential_matches, bitcoin_cli, debug, logging):
        matches = []

        for locator, k in potential_matches:
            for appointment_pos, appointment in enumerate(self.appointments.get(locator)):
                try:
                    # ToDo: Put this back
                    # decrypted_data = decrypt_tx(appointment.encrypted_blob, k, appointment.cypher)
                    # ToDo: Remove this. Temporary hack, since we are not working with blobs but with ids for now
                    # ToDo: just get the raw transaction that matches both parts of the id
                    decrypted_data = bitcoin_cli.getrawtransaction(locator + k)

                    bitcoin_cli.decoderawtransaction(decrypted_data)
                    matches.append((locator, appointment_pos, decrypted_data))

                    if debug:
                        logging.error("[Watcher] Match found for {}:{}! {}".format(locator, appointment_pos, locator+k))
                except JSONRPCException as e:
                    # Tx decode failed returns error code -22, maybe we should be more strict here. Leaving it simple
                    # for the POC
                    if debug:
                        logging.error("[Watcher] Can't build transaction from decoded data. Error code {}".format(e))
                    continue

        return matches


