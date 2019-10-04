from uuid import uuid4
from queue import Queue
from threading import Thread

from pisa import logging
from pisa.responder import Responder
from pisa.conf import MAX_APPOINTMENTS
from pisa.block_processor import BlockProcessor
from pisa.cleaner import Cleaner
from pisa.utils.zmq_subscriber import ZMQHandler


# WIP: MOVED BLOCKCHAIN RELATED TASKS TO BLOCK PROCESSOR IN AN AIM TO MAKE THE CODE MORE MODULAR. THIS SHOULD HELP
#      WITH CODE REUSE WHEN MERGING THE DATA PERSISTENCE PART.


class Watcher:
    def __init__(self, max_appointments=MAX_APPOINTMENTS):
        self.appointments = dict()
        self.locator_uuid_map = dict()
        self.block_queue = None
        self.asleep = True
        self.max_appointments = max_appointments
        self.zmq_subscriber = None
        self.responder = Responder()

    def add_appointment(self, appointment):
        # Rationale:
        # The Watcher will analyze every received block looking for appointment matches. If there is no work
        # to do the watcher can go sleep (if appointments = {} then asleep = True) otherwise for every received block
        # the watcher will get the list of transactions and compare it with the list of appointments.
        # If the watcher is awake, every new appointment will just be added to the appointment list until
        # max_appointments is reached.

        if len(self.appointments) < self.max_appointments:
            # Appointments are identified by the locator: the sha256 of commitment txid (H(tx_id)).
            # Two different nodes may ask for appointments using the same commitment txid, what will result in a
            # collision in our appointments structure (and may be an attack surface). In order to avoid such collisions
            # we will identify every appointment with a uuid

            uuid = uuid4().hex
            self.appointments[uuid] = appointment

            if appointment.locator in self.locator_uuid_map:
                self.locator_uuid_map[appointment.locator].append(uuid)

            else:
                self.locator_uuid_map[appointment.locator] = [uuid]

            if self.asleep:
                self.asleep = False
                self.block_queue = Queue()
                zmq_thread = Thread(target=self.do_subscribe, args=[self.block_queue])
                watcher = Thread(target=self.do_watch)
                zmq_thread.start()
                watcher.start()

                logging.info("[Watcher] waking up!")

            appointment_added = True

            logging.info('[Watcher] new appointment accepted (locator = {})'.format(appointment.locator))

        else:
            appointment_added = False

            logging.info('[Watcher] maximum appointments reached, appointment rejected (locator = {})'.format(
                appointment.locator))

        return appointment_added

    def do_subscribe(self, block_queue):
        self.zmq_subscriber = ZMQHandler(parent='Watcher')
        self.zmq_subscriber.handle(block_queue)

    def do_watch(self):
        while len(self.appointments) > 0:
            block_hash = self.block_queue.get()
            logging.info("[Watcher] new block received {}".format(block_hash))

            block = BlockProcessor.getblock(block_hash)

            if block is not None:
                txids = block.get('tx')

                logging.info("[Watcher] list of transactions: {}".format(txids))

                self.appointments, self.locator_uuid_map = Cleaner.delete_expired_appointment(
                    block, self.appointments, self.locator_uuid_map)

                potential_matches = BlockProcessor.get_potential_matches(txids, self.locator_uuid_map)
                matches = BlockProcessor.get_matches(potential_matches, self.locator_uuid_map, self.appointments)

                for locator, uuid, dispute_txid, justice_txid, justice_rawtx in matches:
                    logging.info("[Watcher] notifying responder about {} and deleting appointment {} (uuid: {})"
                                 .format(justice_txid, locator, uuid))

                    self.responder.add_response(uuid, dispute_txid, justice_txid, justice_rawtx,
                                                self.appointments[uuid].end_time)

                    # Delete the appointment
                    self.appointments.pop(uuid)

                    # If there was only one appointment that matches the locator we can delete the whole list
                    if len(self.locator_uuid_map[locator]) == 1:
                        # ToDo: #9-add-data-persistence
                        self.locator_uuid_map.pop(locator)
                    else:
                        # Otherwise we just delete the appointment that matches locator:appointment_pos
                        # ToDo: #9-add-data-persistence
                        self.locator_uuid_map[locator].remove(uuid)

        # Go back to sleep if there are no more appointments
        self.asleep = True
        self.zmq_subscriber.terminate = True

        logging.error("[Watcher] no more pending appointments, going back to sleep")
