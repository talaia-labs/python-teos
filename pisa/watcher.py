from binascii import hexlify, unhexlify
from queue import Queue
from threading import Thread
from pisa.responder import Responder
from pisa.zmq_subscriber import ZMQHandler
from pisa.utils.authproxy import AuthServiceProxy, JSONRPCException
from hashlib import sha256
from pisa.conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT, MAX_APPOINTMENTS, EXPIRY_DELTA


class Watcher:
    def __init__(self, max_appointments=MAX_APPOINTMENTS):
        self.appointments = dict()
        self.block_queue = None
        self.asleep = True
        self.max_appointments = max_appointments
        self.zmq_subscriber = None
        self.responder = Responder()

    def add_appointment(self, appointment, debug, logging):
        # DISCUSS: about validation of input data

        # Rationale:
        # The Watcher will analyze every received block looking for appointment matches. If there is no work
        # to do the watcher can go sleep (if appointments = {} then asleep = True) otherwise for every received block
        # the watcher will get the list of transactions and compare it with the list of appointments.
        # If the watcher is awake, every new appointment will just be added to the appointment list until
        # max_appointments is reached.

        if len(self.appointments) < self.max_appointments:
            # Appointments are identified by the locator: the sha256 of commitment txid (H(tx_id)).
            # Two different nodes may ask for appointments using the same commitment txid, what will result in a
            # collision in our appointments structure (and may be an attack surface), we use lists to avoid that.
            if not self.appointments.get(appointment.locator):
                self.appointments[appointment.locator] = []

            self.appointments[appointment.locator].append(appointment)

            if self.asleep:
                self.asleep = False
                self.block_queue = Queue()
                zmq_thread = Thread(target=self.do_subscribe, args=[self.block_queue, debug, logging])
                watcher = Thread(target=self.do_watch, args=[debug, logging])
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
                logging.info('[Watcher] maximum appointments reached, appointment rejected (locator = {})'
                             .format(appointment.locator))

        return appointment_added

    def do_subscribe(self, block_queue, debug, logging):
        self.zmq_subscriber = ZMQHandler(parent='Watcher')
        self.zmq_subscriber.handle(block_queue, debug, logging)

    def do_watch(self, debug, logging):
        bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                               BTC_RPC_PORT))

        while len(self.appointments) > 0:
            block_hash = self.block_queue.get()

            try:
                block = bitcoin_cli.getblock(block_hash)
                txids = block.get('tx')

                potential_locators = {sha256(unhexlify(txid)).hexdigest(): txid for txid in txids}

                if debug:
                    logging.info("[Watcher] new block received {}".format(block_hash))
                    logging.info("[Watcher] list of transactions: {}".format(txids))

                # Delete expired appointments
                to_delete = {}
                for locator in self.appointments:
                    for appointment in self.appointments[locator]:
                        if block["height"] > appointment.end_time + EXPIRY_DELTA:
                            # Get the appointment index and add the appointment to the deletion list
                            appointment_pos = self.appointments[locator].index(appointment)

                            if locator in to_delete:
                                to_delete[locator].append(appointment_pos)
                            else:
                                to_delete[locator] = [appointment_pos]

                for locator, indexes in to_delete.items():
                    if len(indexes) == len(self.appointments[locator]):
                        if debug:
                            logging.info("[Watcher] end time reached with no match! Deleting appointment {}"
                                         .format(locator))

                        del self.appointments[locator]
                    else:
                        for i in indexes:
                            if debug:
                                logging.info("[Watcher] end time reached with no match! Deleting appointment {}:{}"
                                             .format(locator, i))

                                del self.appointments[locator][i]

                # Check is any of the tx_ids in the received block is an actual match
                potential_matches = {}
                for locator in self.appointments.keys():
                    if locator in potential_locators:
                        # This is locator:txid
                        potential_matches[locator] = potential_locators[locator]

                if debug:
                    if len(potential_matches) > 0:
                        logging.info("[Watcher] list of potential matches: {}".format(potential_matches))
                    else:
                        logging.info("[Watcher] no potential matches found")

                matches = self.check_potential_matches(potential_matches, bitcoin_cli, debug, logging)

                for locator, appointment_pos, dispute_txid, justice_txid, justice_rawtx in matches:
                    if debug:
                        logging.info("[Watcher] notifying responder about {} and deleting appointment {}:{}".format(
                            justice_txid, locator, appointment_pos))

                    self.responder.add_response(dispute_txid, justice_txid, justice_rawtx,
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
            logging.error("[Watcher] no more pending appointments, going back to sleep")

    def check_potential_matches(self, potential_matches, bitcoin_cli, debug, logging):
        matches = []

        for locator, dispute_txid in potential_matches.items():
            for appointment_pos, appointment in enumerate(self.appointments.get(locator)):
                try:
                    justice_rawtx = appointment.encrypted_blob.decrypt(unhexlify(dispute_txid), debug, logging)
                    justice_rawtx = hexlify(justice_rawtx).decode()
                    justice_txid = bitcoin_cli.decoderawtransaction(justice_rawtx).get('txid')
                    matches.append((locator, appointment_pos, dispute_txid, justice_txid, justice_rawtx))

                    if debug:
                        logging.info("[Watcher] match found for {}:{}! {}".format(locator, appointment_pos,
                                                                                  justice_txid))
                except JSONRPCException as e:
                    # Tx decode failed returns error code -22, maybe we should be more strict here. Leaving it simple
                    # for the POC
                    if debug:
                        logging.error("[Watcher] can't build transaction from decoded data. Error code {}".format(e))
                    continue

        return matches
