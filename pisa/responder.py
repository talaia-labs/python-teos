import json
from queue import Queue
from threading import Thread

from pisa.logger import Logger
from pisa.cleaner import Cleaner
from pisa.carrier import Carrier
from pisa.block_processor import BlockProcessor
from pisa.utils.zmq_subscriber import ZMQHandler

CONFIRMATIONS_BEFORE_RETRY = 6
MIN_CONFIRMATIONS = 6

logger = Logger("Responder")


class Job:
    def __init__(self, locator, dispute_txid, penalty_txid, penalty_rawtx, appointment_end):
        self.locator = locator
        self.dispute_txid = dispute_txid
        self.penalty_txid = penalty_txid
        self.penalty_rawtx = penalty_rawtx
        self.appointment_end = appointment_end

    @classmethod
    def from_dict(cls, job_data):
        locator = job_data.get("locator")
        dispute_txid = job_data.get("dispute_txid")
        penalty_txid = job_data.get("penalty_txid")
        penalty_rawtx = job_data.get("penalty_rawtx")
        appointment_end = job_data.get("appointment_end")

        if any(v is None for v in [locator, dispute_txid, penalty_txid, penalty_rawtx, appointment_end]):
            raise ValueError("Wrong job data, some fields are missing")

        else:
            job = cls(locator, dispute_txid, penalty_txid, penalty_rawtx, appointment_end)

        return job

    def to_dict(self):
        job = {
            "locator": self.locator,
            "dispute_txid": self.dispute_txid,
            "penalty_txid": self.penalty_txid,
            "penalty_rawtx": self.penalty_rawtx,
            "appointment_end": self.appointment_end,
        }

        return job

    def to_json(self):
        return json.dumps(self.to_dict())


class Responder:
    def __init__(self, db_manager):
        self.jobs = dict()
        self.tx_job_map = dict()
        self.unconfirmed_txs = []
        self.missed_confirmations = dict()
        self.asleep = True
        self.block_queue = Queue()
        self.zmq_subscriber = None
        self.db_manager = db_manager

    @staticmethod
    def on_sync(block_hash):
        block_processor = BlockProcessor()
        distance_from_tip = block_processor.get_distance_to_tip(block_hash)

        if distance_from_tip is not None and distance_from_tip > 1:
            synchronized = False

        else:
            synchronized = True

        return synchronized

    def add_response(
        self, uuid, locator, dispute_txid, penalty_txid, penalty_rawtx, appointment_end, block_hash, retry=False
    ):
        if self.asleep:
            logger.info("Waking up")

        carrier = Carrier()
        receipt = carrier.send_transaction(penalty_rawtx, penalty_txid)

        # do_watch can call add_response recursively if a broadcast transaction does not get confirmations
        # retry holds that information. If retry is true the job already exists
        if receipt.delivered:
            if not retry:
                self.create_job(
                    uuid, locator, dispute_txid, penalty_txid, penalty_rawtx, appointment_end, receipt.confirmations
                )

        else:
            # TODO: Add the missing reasons (e.g. RPC_VERIFY_REJECTED)
            # TODO: Use self.on_sync(block_hash) to check whether or not we failed because we are out of sync
            logger.warning("Job failed.", uuid=uuid, on_sync=self.on_sync(block_hash))
            pass

        return receipt

    def create_job(self, uuid, locator, dispute_txid, penalty_txid, penalty_rawtx, appointment_end, confirmations=0):
        job = Job(locator, dispute_txid, penalty_txid, penalty_rawtx, appointment_end)
        self.jobs[uuid] = job

        if penalty_txid in self.tx_job_map:
            self.tx_job_map[penalty_txid].append(uuid)

        else:
            self.tx_job_map[penalty_txid] = [uuid]

        # In the case we receive two jobs with the same penalty txid we only add it to the unconfirmed txs list once
        if penalty_txid not in self.unconfirmed_txs and confirmations == 0:
            self.unconfirmed_txs.append(penalty_txid)

        self.db_manager.store_responder_job(uuid, job.to_json())

        logger.info(
            "New job added.", dispute_txid=dispute_txid, penalty_txid=penalty_txid, appointment_end=appointment_end
        )

        if self.asleep:
            self.asleep = False
            zmq_thread = Thread(target=self.do_subscribe)
            responder = Thread(target=self.do_watch)
            zmq_thread.start()
            responder.start()

    def do_subscribe(self):
        self.zmq_subscriber = ZMQHandler(parent="Responder")
        self.zmq_subscriber.handle(self.block_queue)

    def do_watch(self):
        # ToDo: change prev_block_hash to the last known tip when bootstrapping
        prev_block_hash = BlockProcessor.get_best_block_hash()

        while len(self.jobs) > 0:
            # We get notified for every new received block
            block_hash = self.block_queue.get()
            block = BlockProcessor.get_block(block_hash)

            if block is not None:
                txs = block.get("tx")

                logger.info(
                    "New block received", block_hash=block_hash, prev_block_hash=block.get("previousblockhash"), txs=txs
                )

                if prev_block_hash == block.get("previousblockhash"):
                    self.check_confirmations(txs)

                    height = block.get("height")
                    txs_to_rebroadcast = self.get_txs_to_rebroadcast(txs)
                    completed_jobs = self.get_completed_jobs(height)

                    Cleaner.delete_completed_jobs(completed_jobs, height, self.jobs, self.tx_job_map, self.db_manager)
                    self.rebroadcast(txs_to_rebroadcast, block_hash)

                # NOTCOVERED
                else:
                    logger.warning(
                        "Reorg found",
                        local_prev_block_hash=prev_block_hash,
                        remote_prev_block_hash=block.get("previousblockhash"),
                    )

                    # ToDo: #24-properly-handle-reorgs
                    self.handle_reorgs(block_hash)

                # Register the last processed block for the responder
                self.db_manager.store_last_block_hash_responder(block_hash)

                prev_block_hash = block.get("hash")

        # Go back to sleep if there are no more jobs
        self.asleep = True
        self.zmq_subscriber.terminate = True
        self.block_queue = Queue()

        logger.info("No more pending jobs, going back to sleep")

    def check_confirmations(self, txs):
        # If a new confirmed tx matches a tx we are watching, then we remove it from the unconfirmed txs map
        for tx in txs:
            if tx in self.tx_job_map and tx in self.unconfirmed_txs:
                self.unconfirmed_txs.remove(tx)

                logger.info("Confirmation received for transaction", tx=tx)

        # We also add a missing confirmation to all those txs waiting to be confirmed that have not been confirmed in
        # the current block
        for tx in self.unconfirmed_txs:
            if tx in self.missed_confirmations:
                self.missed_confirmations[tx] += 1

            else:
                self.missed_confirmations[tx] = 1

            logger.info("Transaction missed a confirmation", tx=tx, missed_confirmations=self.missed_confirmations[tx])

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
            if job.appointment_end <= height and job.penalty_txid not in self.unconfirmed_txs:
                tx = Carrier.get_transaction(job.penalty_txid)

                # FIXME: Should be improved with the librarian
                if tx is not None:
                    confirmations = tx.get("confirmations")

                    if confirmations >= MIN_CONFIRMATIONS:
                        # The end of the appointment has been reached
                        completed_jobs.append((uuid, confirmations))

        return completed_jobs

    def rebroadcast(self, txs_to_rebroadcast, block_hash):
        # DISCUSS: #22-discuss-confirmations-before-retry
        # ToDo: #23-define-behaviour-approaching-end

        receipts = []

        for txid in txs_to_rebroadcast:
            self.missed_confirmations[txid] = 0

            for uuid in self.tx_job_map[txid]:
                job = self.jobs[uuid]
                receipt = self.add_response(
                    job.locator,
                    uuid,
                    job.dispute_txid,
                    job.penalty_txid,
                    job.penalty_rawtx,
                    job.appointment_end,
                    block_hash,
                    retry=True,
                )

                logger.warning(
                    "Transaction has missed many confirmations. Rebroadcasting.",
                    penalty_txid=job.penalty_txid,
                    confirmations_missed=CONFIRMATIONS_BEFORE_RETRY,
                )

                receipts.append((txid, receipt))

        return receipts

    # NOTCOVERED
    def handle_reorgs(self, block_hash):
        carrier = Carrier()

        for uuid, job in self.jobs.items():
            # First we check if the dispute transaction is known (exists either in mempool or blockchain)
            dispute_tx = carrier.get_transaction(job.dispute_txid)

            if dispute_tx is not None:
                # If the dispute is there, we check the penalty
                penalty_tx = carrier.get_transaction(job.penalty_txid)

                if penalty_tx is not None:
                    # If the penalty exists we need to check is it's on the blockchain or not so we can update the
                    # unconfirmed transactions list accordingly.
                    if penalty_tx.get("confirmations") is None:
                        self.unconfirmed_txs.append(job.penalty_txid)

                        logger.info(
                            "Penalty transaction back in mempool. Updating unconfirmed transactions.",
                            penalty_txid=job.penalty_txid,
                        )

                else:
                    # If the penalty transaction is missing, we need to reset the job.
                    # DISCUSS: Adding job back, should we flag it as retried?
                    # FIXME: Whether we decide to increase the retried counter or not, the current counter should be
                    #        maintained. There is no way of doing so with the current approach. Update if required
                    self.add_response(
                        job.locator,
                        uuid,
                        job.dispute_txid,
                        job.penalty_txid,
                        job.penalty_rawtx,
                        job.appointment_end,
                        block_hash,
                    )

                    logger.warning("Penalty transaction banished. Resetting the job", penalty_tx=job.penalty_txid)

            else:
                # ToDo: #24-properly-handle-reorgs
                # FIXME: if the dispute is not on chain (either in mempool or not there at all), we need to call the
                #        reorg manager
                logger.warning("Dispute and penalty transaction missing. Calling the reorg manager.")
                logger.error("Reorg manager not yet implemented.")
