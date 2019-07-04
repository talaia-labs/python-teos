from queue import Queue
from threading import Thread
from pisa.zmq_subscriber import ZMQHandler
from pisa.rpc_errors import *
from pisa.tools import check_tx_in_chain
from utils.authproxy import AuthServiceProxy, JSONRPCException
from conf import BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST, BTC_RPC_PORT

CONFIRMATIONS_BEFORE_RETRY = 6
MIN_CONFIRMATIONS = 6


class Job:
    def __init__(self, dispute_txid, justice_rawtx, appointment_end, retry_counter=0):
        self.dispute_txid = dispute_txid
        self.justice_rawtx = justice_rawtx
        self.appointment_end = appointment_end
        self.missed_confirmations = 0
        self.retry_counter = retry_counter


class Responder:
    def __init__(self):
        self.jobs = dict()
        self.confirmation_counter = dict()
        self.block_queue = None
        self.asleep = True
        self.zmq_subscriber = None

    def do_subscribe(self, block_queue, debug, logging):
        self.zmq_subscriber = ZMQHandler(parent='Responder')
        self.zmq_subscriber.handle(block_queue, debug, logging)

    def create_job(self, dispute_txid, justice_txid, justice_rawtx, appointment_end, debug, logging, conf_counter=0,
                   retry=False):
        # DISCUSS: Check what to do if the retry counter gets too big
        if retry:
            self.jobs[justice_txid].retry_counter += 1
            self.jobs[justice_txid].missed_confirmations = 0
        else:
            self.confirmation_counter[justice_txid] = conf_counter
            self.jobs[justice_txid] = Job(dispute_txid, justice_rawtx, appointment_end)

        if debug:
            logging.info('[Responder] new job added (dispute txid = {}, justice txid = {}, appointment end = {})'.
                         format(dispute_txid, justice_txid, appointment_end))

        if self.asleep:
            self.asleep = False
            self.block_queue = Queue()
            zmq_thread = Thread(target=self.do_subscribe, args=[self.block_queue, debug, logging])
            responder = Thread(target=self.handle_responses, args=[debug, logging])
            zmq_thread.start()
            responder.start()

    def add_response(self, dispute_txid, justice_txid, justice_rawtx, appointment_end, debug, logging, retry=False):
        bitcoin_cli = AuthServiceProxy("http://%s:%s@%s:%d" % (BTC_RPC_USER, BTC_RPC_PASSWD, BTC_RPC_HOST,
                                                               BTC_RPC_PORT))
        try:
            if debug:
                if self.asleep:
                    logging.info("[Responder] waking up!")
                logging.info("[Responder] pushing transaction to the network (txid: {})".format(justice_txid))

            bitcoin_cli.sendrawtransaction(justice_rawtx)

            # handle_responses can call add_response recursively if a broadcast transaction does not get confirmations
            # retry holds such information.
            self.create_job(dispute_txid, justice_txid, justice_rawtx, appointment_end, debug, logging, retry=retry)

        except JSONRPCException as e:
            # Since we're pushing a raw transaction to the network we can get two kind of rejections:
            # RPC_VERIFY_REJECTED and RPC_VERIFY_ALREADY_IN_CHAIN. The former implies that the transaction is rejected
            # due to network rules, whereas the later implies that the transaction is already in the blockchain.
            if e.error.get('code') == RPC_VERIFY_REJECTED:
                # DISCUSS: what to do in this case
                pass
            elif e.error.get('code') == RPC_VERIFY_ALREADY_IN_CHAIN:
                try:
                    if debug:
                        logging.info("[Responder] {} is already in the blockchain. Getting the confirmation count and "
                                     "start monitoring the transaction".format(justice_txid))

                    # If the transaction is already in the chain, we get the number of confirmations and watch the job
                    # until the end of the appointment
                    tx_info = bitcoin_cli.getrawtransaction(justice_txid, 1)
                    confirmations = int(tx_info.get("confirmations"))
                    self.create_job(dispute_txid, justice_txid, justice_rawtx, appointment_end, debug, logging,
                                    retry=retry, conf_counter=confirmations)

                except JSONRPCException as e:
                    # While it's quite unlikely, the transaction that was already in the blockchain could have been
                    # reorged while we were querying bitcoind to get the confirmation count. in such a case we just
                    # restart the job
                    if e.error.get('code') == RPC_INVALID_ADDRESS_OR_KEY:
                        self.add_response(dispute_txid, justice_txid, justice_rawtx, appointment_end, debug, logging,
                                          retry=retry)
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
                # Keep count of the confirmations each tx gets
                for job_id, confirmations in self.confirmation_counter.items():
                    # If we see the transaction for the first time, or MIN_CONFIRMATIONS hasn't been reached
                    if job_id in txs or (0 < confirmations):
                        self.confirmation_counter[job_id] += 1

                        if debug:
                            logging.info("[Responder] new confirmation received for txid = {}".format(job_id))

                    elif self.jobs[job_id].missed_confirmations >= CONFIRMATIONS_BEFORE_RETRY:
                        # If a transactions has missed too many confirmations for a while we'll try to rebroadcast
                        # DISCUSS: How many confirmations before retry
                        # DISCUSS: recursion vs setting confirmations to 0 and rebroadcast here
                        # DISCUSS: how many max retries and what to do if the cap is reached
                        self.add_response(self.jobs[job_id].dispute_txid, job_id, self.jobs[job_id].justice_rawtx,
                                          self.jobs[job_id].appointment_end, debug, logging, retry=True)
                        if debug:
                            logging.warning("[Responder] txid = {} has missed {} confirmations. Rebroadcasting"
                                            .format(job_id, CONFIRMATIONS_BEFORE_RETRY))
                    else:
                        # Otherwise we increase the number of missed confirmations
                        self.jobs[job_id].missed_confirmations += 1

                for job_id, job in self.jobs.items():
                    if job.appointment_end <= height and self.confirmation_counter[job_id] >= MIN_CONFIRMATIONS:
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
                if debug:
                    logging.warning("[Responder] reorg found! local prev. block id = {}, remote prev. block id = {}"
                                    .format(prev_block_hash, block.get('previousblockhash')))

                self.handle_reorgs(bitcoin_cli, debug, logging)

            prev_block_hash = block.get('hash')

        # Go back to sleep if there are no more jobs
        self.asleep = True
        self.zmq_subscriber.terminate = True

        if debug:
            logging.info("[Responder] no more pending jobs, going back to sleep")

    def handle_reorgs(self, bitcoin_cli, debug, logging):
        for job_id, job in self.jobs.items():
            # First we check if the dispute transaction is still in the blockchain. If not, the justice can not be
            # there either, so we'll need to call the reorg manager straight away
            dispute_in_chain, _ = check_tx_in_chain(bitcoin_cli, job.dispute_txid, debug, logging, parent='Responder',
                                                    tx_label='dispute')

            # If the dispute is there, we can check the justice tx
            if dispute_in_chain:
                justice_in_chain, justice_confirmations = check_tx_in_chain(bitcoin_cli, job_id, debug, logging,
                                                                            parent='Responder', tx_label='dispute')

                # If both transactions are there, we only need to update the justice tx confirmation count
                if justice_in_chain:
                    if debug:
                        logging.info("[Responder] updating confirmation count for {}: prev. {}, current {}".format(
                            job_id, self.confirmation_counter[job_id], justice_confirmations))
                    self.confirmation_counter[job_id] = justice_confirmations
                    if debug:
                        logging.info("[Responder] no more pending jobs, going back to sleep")

                else:
                    # Otherwise, we will add the job back (implying rebroadcast of the tx) and monitor it again
                    # DISCUSS: Adding job back, should we flag it as retried?
                    self.add_response(job.dispute_txid, job_id, job.justice_rawtx, job.appointment_end, debug, logging)

            else:
                # FIXME: if the dispute is not on chain (either in mempool or not there al all), we need to call the
                #        reorg manager
                logging.warning("[Responder] dispute and justice transaction missing. Calling the reorg manager")
                logging.error("[Responder] reorg manager not yet implemented")
                pass