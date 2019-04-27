from queue import Queue
from threading import Thread
from pisa.zmq_subscriber import ZMQHandler
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException
from conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT


CONFIRMATIONS_BEFORE_RETRY = 6
MIN_CONFIRMATIONS = 6


class Job:
    def __init__(self, dispute_txid, rawtx, appointment_end, retry_counter=0):
        self.dispute_txid = dispute_txid
        self.rawtx = rawtx
        self.appointment_end = appointment_end
        self.in_block_height = None
        self.missed_confirmations = 0
        self.retry_counter = retry_counter


class Responder:
    def __init__(self):
        self.jobs = dict()
        self.confirmation_counter = dict()
        self.block_queue = Queue()
        self.asleep = True

    def add_response(self, dispute_txid, txid, rawtx, appointment_end, debug, logging, retry=False):
        if self.asleep:
            self.asleep = False
            zmq_subscriber = Thread(target=self.do_subscribe, args=[self.block_queue, debug, logging])
            responder = Thread(target=self.handle_responses, args=[debug, logging])
            zmq_subscriber.start()
            responder.start()

        bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                               BTC_RPC_PORT))
        try:
            # ToDo: All errors should be handled as JSONRPCException, check that holds (if so response if no needed)
            response = bitcoin_cli.sendrawtransaction(rawtx)

            # handle_responses can call add_response recursively if a broadcast transaction does not get confirmations
            # retry holds such information.
            # DISCUSS: Check what to do if the retry counter gets too big
            if retry:
                self.jobs[txid].retry_counter += 1
            else:
                self.confirmation_counter[txid] = 0
                self.jobs[txid] = Job(dispute_txid, rawtx, appointment_end)

            if debug:
                logging.info('[Responder] new job added (dispute txid = {}, txid = {}, appointment end = {})'.format(
                    dispute_txid, txid, appointment_end))

        except JSONRPCException as e:
            if debug:
                # ToDo: Check type of error if transaction does not get through
                logging.error("[Responder] JSONRPCException. Error code {}".format(e))

    def handle_responses(self, debug, logging):
        bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                               BTC_RPC_PORT))
        prev_block_hash = None
        while len(self.jobs) > 0:
            # We get notified for every new received block
            block_hash = self.block_queue.get()

            try:
                block = bitcoin_cli.getblock(block_hash)
                txs = block.get('tx')
                height = block.get('height')

                if debug:
                    logging.info("[Responder] new block received {}".format(block_hash))
                    logging.info("[Responder] prev. block hash {}".format(block.get('previousblockhash')))
                    logging.info("[Responder] list of transactions: {}".format(txs))

            except JSONRPCException as e:
                if debug:
                    logging.error("[Responder] couldn't get block from bitcoind. Error code {}".format(e))

                continue

            if prev_block_hash == block.get('previousblockhash'):
                for job_id, job in self.jobs.items():
                    if job.appointment_end <= height:
                        # The end of the appointment has been reached
                        # ToDo: record job in DB
                        del (self.jobs[job_id])
                        if debug:
                            logging.info("[Responder] job completed. Appointment ended at height {}".format(job_id,
                                                                                                            height))

                # Handling new jobs (aka jobs with not enough confirmations), when a job receives MIN_CONFIRMATIONS
                # it will be passed to jobs and we will simply check for chain forks.
                for job_id, confirmations in self.confirmation_counter.items():
                    # If we see the transaction for the first time, or MIN_CONFIRMATIONS hasn't been reached
                    if job_id in txs or (0 < confirmations < MIN_CONFIRMATIONS):
                        confirmations += 1

                        if debug:
                            logging.info("[Responder] new confirmation received for txid = {}".format(job_id))

                    elif self.jobs[job_id].missed_confirmations >= CONFIRMATIONS_BEFORE_RETRY:
                        # If a transactions has missed too many confirmations for a while we'll try to rebroadcast
                        # DISCUSS: How many confirmations before retry
                        # DISCUSS: recursion vs setting confirmations to 0 and rebroadcast here
                        # DISCUSS: how many max retries and what to do if the cap is reached
                        self.add_response(self.jobs[job_id].dispute_txid, job_id, self.jobs[job_id].tx,
                                          self.jobs[job_id].appointment_end, debug, logging, retry=True)
                        if debug:
                            logging.info("[Responder] txid = {} has missed {} confirmations. Rebroadcast"
                                         .format(job_id, CONFIRMATIONS_BEFORE_RETRY))
                    else:
                        # Otherwise we increase the number of missed confirmations
                        self.jobs[job_id].missed_confirmations += 1

            else:
                # ToDo: REORG!!
                if debug:
                    logging.error("[Responder] reorg found! local prev. block id = {}, remote prev. block id = {}"
                                  .format(prev_block_hash, block.get('previousblockhash')))

                self.handle_reorgs(bitcoin_cli, debug, logging)

            prev_block_hash = block.get('previousblockhash')

        # Go back to sleep if there are no more jobs
        self.asleep = True

        if debug:
            logging.error("[Responder] no more pending jobs, going back to sleep.")

    def handle_reorgs(self, bitcoin_cli, debug, logging):
        for job_id, job in self.jobs:
            try:
                tx_info = bitcoin_cli.gettransaction(job_id)
                job.confirmations = int(tx_info.get("confirmations"))

            except JSONRPCException as e:
                # FIXME: It should be safe but check Exception code anyway
                if debug:
                    logging.error("[Responder] justice transaction (txid = {}) not found!".format(job_id))

                try:
                    bitcoin_cli.gettransaction(job.dispute_txid)
                    # DISCUSS: Add job back, should we flag it as retried?
                    self.add_response(job.dispute_txid, job_id, job.rawtx, job.appointment_end, debug, logging)
                except JSONRPCException as e:
                    # FIXME: It should be safe but check Exception code anyway
                    # ToDO: Dispute transaction if not there either, call reorg manager
                    if debug:
                        logging.error("[Responder] dispute transaction (txid = {}) not found either!"
                                      .format(job.dispute_txid))
                    pass

    def do_subscribe(self, block_queue, debug, logging):
        daemon = ZMQHandler()
        daemon.handle(block_queue, debug, logging)
