from queue import Queue
from threading import Thread
from pisa.tools import decrypt_tx
from pisa.responder import Responder
from pisa.zmq_subscriber import ZMQHandler
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT, MAX_APPOINTMENTS


class Watcher:
    def __init__(self, max_appointments=MAX_APPOINTMENTS):
        self.appointments = dict()
        self.block_queue = None
        self.asleep = True
        self.max_appointments = max_appointments
        self.zmq_subscriber = None

    def add_appointment(self, appointment, debug, logging):
        # DISCUSS: about validation of input data

        # Rationale:
        # The Watcher will analyze every received block looking for appointment matches. If there is no work
        # to do the watcher can go sleep (if appointments = {} then asleep = True) otherwise for every received block
        # the watcher will get the list of transactions and compare it with the list of appointments.
        # If the watcher is awake, every new appointment will just be added to the appointment list until
        # max_appointments is reached.

        if len(self.appointments) < self.max_appointments:
            # Appointments are identified by the locator: the most significant 16 bytes of the commitment txid.
            # While 16-byte hash collisions are not likely, they are possible, so we will store appointments in lists
            # even if we only have one (so the code logic is simplified from this point on).
            if not self.appointments.get(appointment.locator):
                self.appointments[appointment.locator] = []

            self.appointments[appointment.locator].append(appointment)

            if self.asleep:
                self.asleep = False
                self.block_queue = Queue()
                zmq_thread = Thread(target=self.do_subscribe, args=[self.block_queue, debug, logging])
                responder = Responder()
                watcher = Thread(target=self.do_watch, args=[responder, debug, logging])
                zmq_thread.start()
                watcher.start()

                if debug:
                    logging.info("[Watcher] waking up!")

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
        self.zmq_subscriber = ZMQHandler(parent='Watcher')
        self.zmq_subscriber.handle(block_queue, debug, logging)

    def do_watch(self, responder, debug, logging):
        bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                               BTC_RPC_PORT))

        while len(self.appointments) > 0:
            block_hash = self.block_queue.get()

            try:
                block = bitcoin_cli.getblock(block_hash)
                txs = block.get('tx')

                if debug:
                    logging.info("[Watcher] new block received {}".format(block_hash))
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

                for locator, appointment_pos, dispute_txid, txid, rawtx in matches:
                    if debug:
                        logging.error("[Watcher] notifying responder about {}:{} and deleting appointment".format(
                            locator, appointment_pos))

                    responder.add_response(dispute_txid, txid, rawtx,
                                           self.appointments[locator][appointment_pos].end_time, debug, logging)

                    # If there was only one appointment that matches the locator we can delete the whole list
                    # DISCUSS: We may want to use locks before adding / removing appointment
                    if len(self.appointments[locator]) == 1:
                        del self.appointments[locator]
                    else:
                        # Otherwise we just delete the appointment that matches locator:appointment_pos
                        del self.appointments[locator][appointment_pos]

            except JSONRPCException as e:
                if debug:
                    logging.error("[Watcher] JSONRPCException. Error code {}".format(e))
                continue

        # Go back to sleep if there are no more appointments
        self.asleep = True
        self.zmq_subscriber.terminate = True

        if debug:
            logging.error("[Watcher] no more pending appointments, going back to sleep.")

    def check_potential_matches(self, potential_matches, bitcoin_cli, debug, logging):
        matches = []

        for locator, k in potential_matches:
            for appointment_pos, appointment in enumerate(self.appointments.get(locator)):
                try:
                    dispute_txid = locator + k
                    raw_tx = appointment.encrypted_blob.decrypt(k)
                    txid = bitcoin_cli.decoderawtransaction(raw_tx).get('txid')
                    matches.append((locator, appointment_pos, dispute_txid, txid, raw_tx))

                    if debug:
                        logging.error("[Watcher] match found for {}:{}! {}".format(locator, appointment_pos,
                                                                                   dispute_txid))
                except JSONRPCException as e:
                    # Tx decode failed returns error code -22, maybe we should be more strict here. Leaving it simple
                    # for the POC
                    if debug:
                        logging.error("[Watcher] can't build transaction from decoded data. Error code {}".format(e))
                    continue

        return matches


