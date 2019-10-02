from queue import Queue
from threading import Thread
from hashlib import sha256
from binascii import unhexlify
from pisa import logging, bitcoin_cli
from pisa.rpc_errors import *
from pisa.tools import check_tx_in_chain
from pisa.utils.zmq_subscriber import ZMQHandler
from pisa.utils.auth_proxy import JSONRPCException

CONFIRMATIONS_BEFORE_RETRY = 6
MIN_CONFIRMATIONS = 6


class Job:
    def __init__(self, dispute_txid, justice_txid, justice_rawtx, appointment_end, confirmations=0, retry_counter=0):
        self.dispute_txid = dispute_txid
        self.justice_txid = justice_txid
        self.justice_rawtx = justice_rawtx
        self.appointment_end = appointment_end
        self.confirmations = confirmations

        self.missed_confirmations = 0
        self.retry_counter = retry_counter

        # FIXME: locator is here so we can give info about jobs for now. It can be either passed from watcher or info
        #        can be directly got from DB
        self.locator = sha256(unhexlify(dispute_txid)).hexdigest()

    def to_json(self):
        job = {"locator": self.locator, "justice_rawtx": self.justice_rawtx, "confirmations": self.confirmations,
               "appointment_end": self.appointment_end}

        return job


class Responder:
    def __init__(self):
        self.jobs = dict()
        self.tx_job_map = dict()
        self.block_queue = None
        self.asleep = True
        self.zmq_subscriber = None

    def add_response(self, uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, retry=False):

        try:
            if self.asleep:
                logging.info("[Responder] waking up!")
            logging.info("[Responder] pushing transaction to the network (txid: {})".format(justice_txid))

            bitcoin_cli.sendrawtransaction(justice_rawtx)

            # handle_responses can call add_response recursively if a broadcast transaction does not get confirmations
            # retry holds such information.
            self.create_job(uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, retry=retry)

        except JSONRPCException as e:
            self.handle_send_failures(e, uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, retry)

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

        logging.info('[Responder] new job added (dispute txid = {}, justice txid = {}, appointment end = {})'
                     .format(dispute_txid, justice_txid, appointment_end))

        if self.asleep:
            self.asleep = False
            self.block_queue = Queue()
            zmq_thread = Thread(target=self.do_subscribe, args=[self.block_queue])
            responder = Thread(target=self.handle_responses)
            zmq_thread.start()
            responder.start()

    def do_subscribe(self, block_queue):
        self.zmq_subscriber = ZMQHandler(parent='Responder')
        self.zmq_subscriber.handle(block_queue)

    def handle_responses(self):
        prev_block_hash = 0
        while len(self.jobs) > 0:
            # We get notified for every new received block
            block_hash = self.block_queue.get()

            try:
                block = bitcoin_cli.getblock(block_hash)
                txs = block.get('tx')
                height = block.get('height')

                logging.info("[Responder] new block received {}".format(block_hash))
                logging.info("[Responder] prev. block hash {}".format(block.get('previousblockhash')))
                logging.info("[Responder] list of transactions: {}".format(txs))

            except JSONRPCException as e:
                logging.error("[Responder] couldn't get block from bitcoind. Error code {}".format(e))

                continue

            completed_jobs = []
            if prev_block_hash == block.get('previousblockhash') or prev_block_hash == 0:
                # Keep count of the confirmations each tx gets
                for justice_txid, jobs in self.tx_job_map.items():
                    for uuid in jobs:
                        if justice_txid in txs or self.jobs[uuid].confirmations > 0:
                            self.jobs[uuid].confirmations += 1

                            logging.info("[Responder] new confirmation received for job = {}, txid = {}".format(
                                uuid, justice_txid))

                        elif self.jobs[uuid].missed_confirmations >= CONFIRMATIONS_BEFORE_RETRY:
                            # If a transactions has missed too many confirmations for a while we'll try to rebroadcast
                            # ToDO: #22-discuss-confirmations-before-retry
                            # ToDo: #23-define-behaviour-approaching-end
                            self.add_response(uuid, self.jobs[uuid].dispute_txid, justice_txid,
                                              self.jobs[uuid].justice_rawtx, self.jobs[uuid].appointment_end,
                                              retry=True)

                            logging.warning("[Responder] txid = {} has missed {} confirmations. Rebroadcasting"
                                            .format(justice_txid, CONFIRMATIONS_BEFORE_RETRY))

                        else:
                            # Otherwise we increase the number of missed confirmations
                            self.jobs[uuid].missed_confirmations += 1

                        if self.jobs[uuid].appointment_end <= height and self.jobs[uuid].confirmations >= \
                                MIN_CONFIRMATIONS:
                            # The end of the appointment has been reached
                            completed_jobs.append(uuid)

                self.remove_completed_jobs(completed_jobs, height)

            else:
                logging.warning("[Responder] reorg found! local prev. block id = {}, remote prev. block id = {}"
                                .format(prev_block_hash, block.get('previousblockhash')))

                self.handle_reorgs()

            prev_block_hash = block.get('hash')

        # Go back to sleep if there are no more jobs
        self.asleep = True
        self.zmq_subscriber.terminate = True

        logging.info("[Responder] no more pending jobs, going back to sleep")

    def handle_send_failures(self, e, uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, retry):
        # Since we're pushing a raw transaction to the network we can get two kind of rejections:
        # RPC_VERIFY_REJECTED and RPC_VERIFY_ALREADY_IN_CHAIN. The former implies that the transaction is rejected
        # due to network rules, whereas the later implies that the transaction is already in the blockchain.
        if e.error.get('code') == RPC_VERIFY_REJECTED:
            # DISCUSS: what to do in this case
            # DISCUSS: invalid transactions (properly formatted but invalid, like unsigned) fit here too.
            # DISCUSS: RPC_VERIFY_ERROR could also be a possible case.
            # DISCUSS: check errors -9 and -10
            pass

        elif e.error.get('code') == RPC_VERIFY_ALREADY_IN_CHAIN:
            try:
                logging.info("[Responder] {} is already in the blockchain. Getting the confirmation count and start "
                             "monitoring the transaction".format(justice_txid))

                # If the transaction is already in the chain, we get the number of confirmations and watch the job
                # until the end of the appointment
                tx_info = bitcoin_cli.getrawtransaction(justice_txid, 1)
                confirmations = int(tx_info.get("confirmations"))
                self.create_job(uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, retry=retry,
                                confirmations=confirmations)

            except JSONRPCException as e:
                # While it's quite unlikely, the transaction that was already in the blockchain could have been
                # reorged while we were querying bitcoind to get the confirmation count. In such a case we just
                # restart the job
                if e.error.get('code') == RPC_INVALID_ADDRESS_OR_KEY:
                    self.add_response(uuid, dispute_txid, justice_txid, justice_rawtx, appointment_end, retry=retry)

                else:
                    # If something else happens (unlikely but possible) log it so we can treat it in future releases
                    logging.error("[Responder] JSONRPCException. Error {}".format(e))

        else:
            # If something else happens (unlikely but possible) log it so we can treat it in future releases
            logging.error("[Responder] JSONRPCException. Error {}".format(e))

    def remove_completed_jobs(self, completed_jobs, height):
        for uuid in completed_jobs:
            logging.info("[Responder] job completed (uuid = {}, justice_txid = {}). Appointment ended at "
                         "block {} after {} confirmations".format(uuid, self.jobs[uuid].justice_txid, height,
                                                                  self.jobs[uuid].confirmations))

            # ToDo: #9-add-data-persistency
            justice_txid = self.jobs[uuid].justice_txid
            self.jobs.pop(uuid)

            if len(self.tx_job_map[justice_txid]) == 1:
                self.tx_job_map.pop(justice_txid)

                logging.info("[Responder] no more jobs for justice_txid {}".format(justice_txid))

            else:
                self.tx_job_map[justice_txid].remove(uuid)

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
                pass
