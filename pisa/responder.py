import json
from queue import Queue
from hashlib import sha256
from threading import Thread
from binascii import unhexlify

from pisa.logger import Logger
from pisa.cleaner import Cleaner
from pisa.carrier import Carrier
from pisa.tools import check_tx_in_chain
from pisa.block_processor import BlockProcessor
from pisa.utils.zmq_subscriber import ZMQHandler

CONFIRMATIONS_BEFORE_RETRY = 6
MIN_CONFIRMATIONS = 6

logger = Logger("Responder")


class Job:
    def __init__(self, dispute_txid, justice_txid, justice_rawtx, appointment_end):
        self.dispute_txid = dispute_txid
        self.justice_txid = justice_txid
        self.justice_rawtx = justice_rawtx
        self.appointment_end = appointment_end

        # FIXME: locator is here so we can give info about jobs for now. It can be either passed from watcher or info
        #        can be directly got from DB
        self.locator = sha256(unhexlify(dispute_txid)).hexdigest()

    def to_dict(self):
        job = {"locator": self.locator, "justice_rawtx": self.justice_rawtx, "appointment_end": self.appointment_end}

        return job

    def to_json(self):
        return json.dumps(self.to_dict())


class Responder:
    def __init__(self, db_manager):
        self.jobs = dict()
        self.tx_job_map = dict()
        self.unconfirmed_txs = []
        self.missed_confirmations = dict()
        self.block_queue = None
        self.asleep = True
        self.zmq_subscriber = None
        self.db_manager = db_manager

    def add_response(self, uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, retry=False):
        if self.asleep:
            logger.info("Waking up")

        carrier = Carrier()
        receipt = carrier.send_transaction(justice_rawtx, justice_txid)

        # do_watch can call add_response recursively if a broadcast transaction does not get confirmations
        # retry holds that information. If retry is true the job already exists
        if receipt.delivered:
            if not retry:
                self.create_job(uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, receipt.confirmations)

        else:
            # TODO: Add the missing reasons (e.g. RPC_VERIFY_REJECTED)
            pass

        return receipt

    def create_job(self, uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, confirmations=0):
        job = Job(dispute_txid, justice_txid, justice_rawtx, appointment_end)
        self.jobs[uuid] = job

        if justice_txid in self.tx_job_map:
            self.tx_job_map[justice_txid].append(uuid)

        else:
            self.tx_job_map[justice_txid] = [uuid]

        if confirmations == 0:
            self.unconfirmed_txs.append(justice_txid)

        self.db_manager.store_responder_job(uuid.encode, job.to_json())

        logger.info("New job added.", dispute_txid=dispute_txid, justice_txid=justice_txid,
                    appointment_end=appointment_end)

        if self.asleep:
            self.asleep = False
            self.block_queue = Queue()
            zmq_thread = Thread(target=self.do_subscribe)
            responder = Thread(target=self.do_watch)
            zmq_thread.start()
            responder.start()

    def do_subscribe(self):
        self.zmq_subscriber = ZMQHandler(parent='Responder')
        self.zmq_subscriber.handle(self.block_queue)

    def do_watch(self):
        # ToDo: #9-add-data-persistence
        #       change prev_block_hash to the last known tip when bootstrapping
        prev_block_hash = BlockProcessor.get_best_block_hash()

        while len(self.jobs) > 0:
            # We get notified for every new received block
            block_hash = self.block_queue.get()
            block = BlockProcessor.get_block(block_hash)

            if block is not None:
                txs = block.get('tx')
                height = block.get('height')

                logger.info("New block received",
                            block_hash=block_hash, prev_block_hash=block.get('previousblockhash'), txs=txs)

                # ToDo: #9-add-data-persistence
                if prev_block_hash == block.get('previousblockhash'):
                    self.unconfirmed_txs, self.missed_confirmations = BlockProcessor.check_confirmations(
                        txs, self.unconfirmed_txs, self.tx_job_map, self.missed_confirmations)

                    txs_to_rebroadcast = self.get_txs_to_rebroadcast(txs)
                    completed_jobs = self.get_completed_jobs(height)

                    Cleaner.delete_completed_jobs(self.jobs, self.tx_job_map, completed_jobs, height)
                    self.rebroadcast(txs_to_rebroadcast)

                # NOTCOVERED
                else:
                    logger.warning("Reorg found", local_prev_block_hash=prev_block_hash,
                                   remote_prev_block_hash=block.get('previousblockhash'))

                    # ToDo: #24-properly-handle-reorgs
                    self.handle_reorgs()

                # Register the last processed block for the responder
                self.db_manager.store_last_block_responder(block_hash)

                prev_block_hash = block.get('hash')

        # Go back to sleep if there are no more jobs
        self.asleep = True
        self.zmq_subscriber.terminate = True

        logger.info("No more pending jobs, going back to sleep")

    def get_txs_to_rebroadcast(self, txs):
        txs_to_rebroadcast = []

        for tx in txs:
            if tx in self.missed_confirmations and self.missed_confirmations[tx] >= CONFIRMATIONS_BEFORE_RETRY:
                # If a transactions has missed too many confirmations we add it to the rebroadcast list
                txs_to_rebroadcast.append(tx)

        return txs_to_rebroadcast

    def get_completed_jobs(self, height):
        completed_jobs = []

        for uuid, job in self.jobs.items():
            if job.appointment_end <= height and job.justice_txid not in self.unconfirmed_txs:
                tx = Carrier.get_transaction(job.justice_txid)

                # FIXME: Should be improved with the librarian
                if tx is not None:
                    confirmations = tx.get('confirmations')

                    if confirmations >= MIN_CONFIRMATIONS:
                        # The end of the appointment has been reached
                        completed_jobs.append((uuid, confirmations))

        return completed_jobs

    def rebroadcast(self, txs_to_rebroadcast):
        # DISCUSS: #22-discuss-confirmations-before-retry
        # ToDo: #23-define-behaviour-approaching-end

        receipts = []

        for txid in txs_to_rebroadcast:
            self.missed_confirmations[txid] = 0

            for uuid in self.tx_job_map[txid]:
                job = self.jobs[uuid]
                receipt = self.add_response(uuid, job.dispute_txid, job.justice_txid, job.justice_rawtx,
                                            job.appointment_end, retry=True)

                logger.warning("Transaction has missed many confirmations. Rebroadcasting.",
                               justice_txid=job.justice_txid, confirmations_missed=CONFIRMATIONS_BEFORE_RETRY)

                receipts.append((txid, receipt))

        return receipts

    # FIXME: Legacy code, must be checked and updated/fixed
    # NOTCOVERED
    def handle_reorgs(self):
        for uuid, job in self.jobs.items():
            # First we check if the dispute transaction is still in the blockchain. If not, the justice can not be
            # there either, so we'll need to call the reorg manager straight away
            dispute_in_chain, _ = check_tx_in_chain(job.dispute_txid, logger=logger, tx_label='Dispute tx')

            # If the dispute is there, we can check the justice tx
            if dispute_in_chain:
                justice_in_chain, justice_confirmations = check_tx_in_chain(job.justice_txid, logger=logger,
                                                                            tx_label='Justice tx')

                # If both transactions are there, we only need to update the justice tx confirmation count
                if justice_in_chain:
                    logger.info("Updating confirmation count for transaction.",
                                justice_txid=job.justice_txid,
                                prev_count=job.confirmations,
                                curr_count=justice_confirmations)

                    job.confirmations = justice_confirmations

                else:
                    # Otherwise, we will add the job back (implying rebroadcast of the tx) and monitor it again
                    # DISCUSS: Adding job back, should we flag it as retried?
                    # FIXME: Whether we decide to increase the retried counter or not, the current counter should be
                    #        maintained. There is no way of doing so with the current approach. Update if required
                    self.add_response(uuid, job.dispute_txid, job.justice_txid, job.justice_rawtx, job.appointment_end)

            else:
                # ToDo: #24-properly-handle-reorgs
                # FIXME: if the dispute is not on chain (either in mempool or not there at all), we need to call the
                #        reorg manager
                logger.warning("Dispute and justice transaction missing. Calling the reorg manager")
                logger.error("Reorg manager not yet implemented")
