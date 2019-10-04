from queue import Queue
from threading import Thread
from hashlib import sha256
from binascii import unhexlify

from pisa.cleaner import Cleaner
from pisa.carrier import Carrier
from pisa import logging
from pisa.tools import check_tx_in_chain
from pisa.block_processor import BlockProcessor
from pisa.utils.zmq_subscriber import ZMQHandler

CONFIRMATIONS_BEFORE_RETRY = 6
MIN_CONFIRMATIONS = 6


class Job:
    def __init__(self, dispute_txid, justice_txid, justice_rawtx, appointment_end, retry_counter=0):
        self.dispute_txid = dispute_txid
        self.justice_txid = justice_txid
        self.justice_rawtx = justice_rawtx
        self.appointment_end = appointment_end

        self.retry_counter = retry_counter

        # FIXME: locator is here so we can give info about jobs for now. It can be either passed from watcher or info
        #        can be directly got from DB
        self.locator = sha256(unhexlify(dispute_txid)).hexdigest()

    def to_json(self):
        job = {"locator": self.locator, "justice_rawtx": self.justice_rawtx, "appointment_end": self.appointment_end}

        return job


class Responder:
    def __init__(self):
        self.jobs = dict()
        self.tx_job_map = dict()
        self.unconfirmed_txs = []
        self.missed_confirmations = dict()
        self.block_queue = None
        self.asleep = True
        self.zmq_subscriber = None

    def add_response(self, uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, retry=False):
        if self.asleep:
            logging.info("[Responder] waking up!")

        carrier = Carrier()
        receipt = carrier.send_transaction(justice_rawtx, justice_txid)

        if receipt.delivered:
            # do_watch can call add_response recursively if a broadcast transaction does not get confirmations
            # retry holds such information.
            self.create_job(uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, retry=retry,
                            confirmations=receipt.confirmations)

        else:
            # TODO: Add the missing reasons (e.g. RPC_VERIFY_REJECTED)
            pass

    def create_job(self, uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, confirmations=0,
                   retry=False):

        # ToDo: #23-define-behaviour-approaching-end
        if retry:
            self.jobs[uuid].retry_counter += 1
            self.jobs[uuid].missed_confirmations = 0

        else:
            self.jobs[uuid] = Job(dispute_txid, justice_txid, justice_rawtx, appointment_end, confirmations)

            if justice_txid in self.tx_job_map:
                self.tx_job_map[justice_txid].append(uuid)

            else:
                self.tx_job_map[justice_txid] = [uuid]

            if confirmations == 0:
                self.unconfirmed_txs.append(justice_txid)

        logging.info('[Responder] new job added (dispute txid = {}, justice txid = {}, appointment end = {})'
                     .format(dispute_txid, justice_txid, appointment_end))

        if self.asleep:
            self.asleep = False
            self.block_queue = Queue()
            zmq_thread = Thread(target=self.do_subscribe, args=[self.block_queue])
            responder = Thread(target=self.do_watch)
            zmq_thread.start()
            responder.start()

    def do_subscribe(self, block_queue):
        self.zmq_subscriber = ZMQHandler(parent='Responder')
        self.zmq_subscriber.handle(block_queue)

    def do_watch(self):
        # ToDo: #9-add-data-persistence
        #       change prev_block_hash to the last known tip when bootstrapping
        prev_block_hash = 0

        while len(self.jobs) > 0:
            # We get notified for every new received block
            block_hash = self.block_queue.get()
            block = BlockProcessor.get_block(block_hash)

            if block is not None:
                txs = block.get('tx')
                height = block.get('height')

                logging.info("[Responder] new block received {}".format(block_hash))
                logging.info("[Responder] prev. block hash {}".format(block.get('previousblockhash')))
                logging.info("[Responder] list of transactions: {}".format(txs))

                # ToDo: #9-add-data-persistence
                #       change prev_block_hash condition
                if prev_block_hash == block.get('previousblockhash') or prev_block_hash == 0:
                    self.unconfirmed_txs, self.missed_confirmations = BlockProcessor.check_confirmations(
                        txs, self.unconfirmed_txs, self.tx_job_map, self.missed_confirmations)

                    txs_to_rebroadcast = self.get_txs_to_rebroadcast(txs)
                    self.jobs, self.tx_job_map = Cleaner.delete_completed_jobs(self.jobs, self.tx_job_map,
                                                                               self.get_completed_jobs(height), height)

                    self.rebroadcast(txs_to_rebroadcast)

                else:
                    logging.warning("[Responder] reorg found! local prev. block id = {}, remote prev. block id = {}"
                                    .format(prev_block_hash, block.get('previousblockhash')))

                    self.handle_reorgs()

                prev_block_hash = block.get('hash')

        # Go back to sleep if there are no more jobs
        self.asleep = True
        self.zmq_subscriber.terminate = True

        logging.info("[Responder] no more pending jobs, going back to sleep")

    def get_txs_to_rebroadcast(self, txs):
        txs_to_rebroadcast = []

        for tx in txs:
            if self.missed_confirmations[tx] >= CONFIRMATIONS_BEFORE_RETRY:
                # If a transactions has missed too many confirmations we add it to the rebroadcast list
                txs_to_rebroadcast.append(tx)

        return txs_to_rebroadcast

    def get_completed_jobs(self, height):
        completed_jobs = []

        for uuid, job in self.jobs:
            if job.appointment_end <= height:
                tx = Carrier.get_transaction(job.dispute_txid)

                # FIXME: Should be improved with the librarian
                if tx is not None and tx.get('confirmations') > MIN_CONFIRMATIONS:
                    # The end of the appointment has been reached
                    completed_jobs.append(uuid)

        return completed_jobs

    def rebroadcast(self, jobs_to_rebroadcast):
        # ToDO: #22-discuss-confirmations-before-retry
        # ToDo: #23-define-behaviour-approaching-end

        for tx in jobs_to_rebroadcast:
            for uuid in self.tx_job_map[tx]:
                self.add_response(uuid, self.jobs[uuid].dispute_txid, self.jobs[uuid].justice_txid,
                                  self.jobs[uuid].justice_rawtx, self.jobs[uuid].appointment_end, retry=True)

                logging.warning("[Responder] tx {} has missed {} confirmations. Rebroadcasting"
                                .format(self.jobs[uuid].justice_txid, CONFIRMATIONS_BEFORE_RETRY))

    # FIXME: Legacy code, must be checked and updated/fixed
    def handle_reorgs(self):
        for uuid, job in self.jobs.items():
            # First we check if the dispute transaction is still in the blockchain. If not, the justice can not be
            # there either, so we'll need to call the reorg manager straight away
            dispute_in_chain, _ = check_tx_in_chain(job.dispute_txid, parent='Responder', tx_label='dispute tx')

            # If the dispute is there, we can check the justice tx
            if dispute_in_chain:
                justice_in_chain, justice_confirmations = check_tx_in_chain(job.justice_txid, parent='Responder',
                                                                            tx_label='justice tx')

                # If both transactions are there, we only need to update the justice tx confirmation count
                if justice_in_chain:
                    logging.info("[Responder] updating confirmation count for {}: prev. {}, current {}".format(
                            job.justice_txid, job.confirmations, justice_confirmations))

                    job.confirmations = justice_confirmations

                else:
                    # Otherwise, we will add the job back (implying rebroadcast of the tx) and monitor it again
                    # DISCUSS: Adding job back, should we flag it as retried?
                    # FIXME: Whether we decide to increase the retried counter or not, the current counter should be
                    #        maintained. There is no way of doing so with the current approach. Update if required
                    self.add_response(uuid, job.dispute_txid, job.justice_txid, job.justice_rawtx, job.appointment_end)

            else:
                # ToDo: #24-properly-handle-reorgs
                # FIXME: if the dispute is not on chain (either in mempool or not there al all), we need to call the
                #        reorg manager
                logging.warning("[Responder] dispute and justice transaction missing. Calling the reorg manager")
                logging.error("[Responder] reorg manager not yet implemented")
