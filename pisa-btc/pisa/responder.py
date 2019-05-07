from queue import Queue
from threading import Thread
from pisa.zmq_subscriber import ZMQHandler
from pisa.errors import *
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
        self.block_queue = None
        self.asleep = True
        self.zmq_subscriber = None

    def create_job(self, dispute_txid, txid, rawtx, appointment_end, debug, logging, conf_counter=0, retry=False):
        # DISCUSS: Check what to do if the retry counter gets too big
        if retry:
            self.jobs[txid].retry_counter += 1
        else:
            self.confirmation_counter[txid] = conf_counter
            self.jobs[txid] = Job(dispute_txid, rawtx, appointment_end)

        if debug:
            logging.info('[Responder] new job added (dispute txid = {}, txid = {}, appointment end = {})'.format(
                dispute_txid, txid, appointment_end))

        if self.asleep:
            self.asleep = False
            self.block_queue = Queue()
            zmq_thread = Thread(target=self.do_subscribe, args=[self.block_queue, debug, logging])
            responder = Thread(target=self.handle_responses, args=[debug, logging])
            zmq_thread.start()
            responder.start()

    def add_response(self, dispute_txid, txid, rawtx, appointment_end, debug, logging, retry=False):
        bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                               BTC_RPC_PORT))
        try:
            # ToDo: All errors should be handled as JSONRPCException, check that holds (if so response if no needed)
            if debug:
                if self.asleep:
                    logging.info("[Responder] waking up!")
                logging.info("[Responder] pushing transaction to the network (txid: {})".format(txid))

            bitcoin_cli.sendrawtransaction(rawtx)

            # handle_responses can call add_response recursively if a broadcast transaction does not get confirmations
            # retry holds such information.
            self.create_job(dispute_txid, txid, rawtx, appointment_end, debug, logging, conf_counter=0, retry=retry)

        except JSONRPCException as e:
            # Since we're pushing a raw transaction to the network we can get two kind of rejections:
            # RPC_VERIFY_REJECTED and RPC_VERIFY_ALREADY_IN_CHAIN. The former implies that the transaction is rejected
            # due to network rules, whereas the later implies that the transaction is already in the blockchain.
            if e.code == RPC_VERIFY_REJECTED:
                # DISCUSS: what to do in this case
                pass
            elif e.code == RPC_VERIFY_ALREADY_IN_CHAIN:
                try:
                    # If the transaction is already in the chain, we get the number of confirmations and watch the job
                    # until the end of the appointment
                    tx_info = bitcoin_cli.gettransaction(txid)
                    confirmations = int(tx_info.get("confirmations"))
                    self.create_job(dispute_txid, txid, rawtx, appointment_end, debug, logging, retry=retry,
                                    conf_counter=confirmations)
                except JSONRPCException as e:
                    # While it's quite unlikely, the transaction that was already in the blockchain could have been
                    # reorged while we were querying bitcoind to get the confirmation count. in such a case we just
                    # restart the job
                    if e.code == RPC_INVALID_ADDRESS_OR_KEY:
                        self.add_response(dispute_txid, txid, rawtx, appointment_end, debug, logging, retry=retry)
                    elif debug:
                        # If something else happens (unlikely but possible) log it so we can treat it in future releases
                        logging.error("[Responder] JSONRPCException. Error code {}".format(e))
            elif debug:
                # If something else happens (unlikely but possible) log it so we can treat it in future releases
                logging.error("[Responder] JSONRPCException. Error code {}".format(e))

    def handle_responses(self, debug, logging):
        bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                               BTC_RPC_PORT))
        prev_block_hash = 0
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

            jobs_to_delete = []
            if prev_block_hash == block.get('previousblockhash') or prev_block_hash == 0:
                # Handling new jobs (aka jobs with not enough confirmations), when a job receives MIN_CONFIRMATIONS
                # it will be passed to jobs and we will simply check for chain forks.
                for job_id, confirmations in self.confirmation_counter.items():
                    # If we see the transaction for the first time, or MIN_CONFIRMATIONS hasn't been reached
                    if job_id in txs or (0 < confirmations < MIN_CONFIRMATIONS):
                        self.confirmation_counter[job_id] += 1

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

                for job_id, job in self.jobs.items():
                    if job.appointment_end <= height:
                        # The end of the appointment has been reached
                        jobs_to_delete.append(job_id)

                for job_id in jobs_to_delete:
                    # Trying to delete directly when iterating the last for causes dictionary changed size error during
                    # iteration in Python3 (can not be solved iterating only trough keys in Python3 either)

                    if debug:
                        logging.info("[Responder] {} completed. Appointment ended at block {} after {} confirmations"
                                     .format(job_id, height, self.confirmation_counter[job_id]))

                    # ToDo: record job in DB
                    del self.jobs[job_id]
                    del self.confirmation_counter[job_id]

            else:
                # ToDo: REORG!!
                if debug:
                    logging.error("[Responder] reorg found! local prev. block id = {}, remote prev. block id = {}"
                                  .format(prev_block_hash, block.get('previousblockhash')))

                self.handle_reorgs(bitcoin_cli, debug, logging)

            prev_block_hash = block.get('hash')

        # Go back to sleep if there are no more jobs
        self.asleep = True
        self.zmq_subscriber.terminate = True

        if debug:
            logging.error("[Responder] no more pending jobs, going back to sleep.")

    def handle_reorgs(self, bitcoin_cli, debug, logging):
        for job_id, job in self.jobs.items():
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
        self.zmq_subscriber = ZMQHandler(parent='Responder')
        self.zmq_subscriber.handle(block_queue, debug, logging)
