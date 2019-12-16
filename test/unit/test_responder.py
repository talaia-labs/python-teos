import json
import pytest
import random
from uuid import uuid4
from shutil import rmtree
from copy import deepcopy
from threading import Thread
from queue import Queue, Empty

from pisa import c_logger
from pisa.db_manager import DBManager
from pisa.responder import Responder, Job
from pisa.block_processor import BlockProcessor
from pisa.tools import bitcoin_cli

from common.constants import LOCATOR_LEN_HEX
from common.tools import check_sha256_hex_format

from test.simulator.utils import sha256d
from test.simulator.bitcoind_sim import TX
from test.unit.conftest import generate_block, generate_blocks, get_random_value_hex

c_logger.disabled = True


@pytest.fixture(scope="module")
def responder(db_manager):
    return Responder(db_manager)


@pytest.fixture()
def temp_db_manager():
    db_name = get_random_value_hex(8)
    db_manager = DBManager(db_name)
    yield db_manager

    db_manager.db.close()
    rmtree(db_name)


def create_dummy_job_data(random_txid=False, justice_rawtx=None):
    # The following transaction data corresponds to a valid transaction. For some test it may be interesting to have
    # some valid data, but for others we may need multiple different justice_txids.

    dispute_txid = "0437cd7f8525ceed2324359c2d0ba26006d92d856a9c20fa0241106ee5a597c9"
    justice_txid = "f4184fc596403b9d638783cf57adfe4c75c605f6356fbc91338530e9831e9e16"

    if justice_rawtx is None:
        justice_rawtx = (
            "0100000001c997a5e56e104102fa209c6a852dd90660a20b2d9c352423edce25857fcd3704000000004847304402"
            "204e45e16932b8af514961a1d3a1a25fdf3f4f7732e9d624c6c61548ab5fb8cd410220181522ec8eca07de4860a4"
            "acdd12909d831cc56cbbac4622082221a8768d1d0901ffffffff0200ca9a3b00000000434104ae1a62fe09c5f51b"
            "13905f07f06b99a2f7159b2225f374cd378d71302fa28414e7aab37397f554a7df5f142c21c1b7303b8a0626f1ba"
            "ded5c72a704f7e6cd84cac00286bee0000000043410411db93e1dcdb8a016b49840f8c53bc1eb68a382e97b1482e"
            "cad7b148a6909a5cb2e0eaddfb84ccf9744464f82e160bfa9b8b64f9d4c03f999b8643f656b412a3ac00000000"
        )

    else:
        justice_txid = sha256d(justice_rawtx)

    if random_txid is True:
        justice_txid = get_random_value_hex(32)

    appointment_end = bitcoin_cli().getblockcount() + 2
    locator = dispute_txid[:LOCATOR_LEN_HEX]

    return locator, dispute_txid, justice_txid, justice_rawtx, appointment_end


def create_dummy_job(random_txid=False, justice_rawtx=None):
    locator, dispute_txid, justice_txid, justice_rawtx, appointment_end = create_dummy_job_data(
        random_txid, justice_rawtx
    )
    return Job(locator, dispute_txid, justice_txid, justice_rawtx, appointment_end)


def test_job_init(run_bitcoind):
    locator, dispute_txid, justice_txid, justice_rawtx, appointment_end = create_dummy_job_data()
    job = Job(locator, dispute_txid, justice_txid, justice_rawtx, appointment_end)

    assert (
        job.dispute_txid == dispute_txid
        and job.justice_txid == justice_txid
        and job.justice_rawtx == justice_rawtx
        and job.appointment_end == appointment_end
    )


def test_on_sync(run_bitcoind, responder):
    # We're on sync if we're 1 or less blocks behind the tip
    chain_tip = BlockProcessor.get_best_block_hash()
    assert Responder.on_sync(chain_tip) is True

    generate_block()
    assert Responder.on_sync(chain_tip) is True


def test_on_sync_fail(responder):
    # This should fail if we're more than 1 block behind the tip
    chain_tip = BlockProcessor.get_best_block_hash()
    generate_blocks(2)

    assert Responder.on_sync(chain_tip) is False


def test_job_to_dict():
    job = create_dummy_job()
    job_dict = job.to_dict()

    assert (
        job.locator == job_dict["locator"]
        and job.justice_rawtx == job_dict["justice_rawtx"]
        and job.appointment_end == job_dict["appointment_end"]
    )


def test_job_to_json():
    job = create_dummy_job()
    job_dict = json.loads(job.to_json())

    assert (
        job.locator == job_dict["locator"]
        and job.justice_rawtx == job_dict["justice_rawtx"]
        and job.appointment_end == job_dict["appointment_end"]
    )


def test_job_from_dict():
    job_dict = create_dummy_job().to_dict()
    new_job = Job.from_dict(job_dict)

    assert job_dict == new_job.to_dict()


def test_job_from_dict_invalid_data():
    job_dict = create_dummy_job().to_dict()

    for value in ["dispute_txid", "justice_txid", "justice_rawtx", "appointment_end"]:
        job_dict_copy = deepcopy(job_dict)
        job_dict_copy[value] = None

        try:
            Job.from_dict(job_dict_copy)
            assert False

        except ValueError:
            assert True


def test_init_responder(responder):
    assert type(responder.jobs) is dict and len(responder.jobs) == 0
    assert type(responder.tx_job_map) is dict and len(responder.tx_job_map) == 0
    assert type(responder.unconfirmed_txs) is list and len(responder.unconfirmed_txs) == 0
    assert type(responder.missed_confirmations) is dict and len(responder.missed_confirmations) == 0
    assert responder.block_queue.empty()
    assert responder.asleep is True
    assert responder.zmq_subscriber is None


def test_add_response(db_manager):
    responder = Responder(db_manager)
    uuid = uuid4().hex
    job = create_dummy_job()

    # The block_hash passed to add_response does not matter much now. It will in the future to deal with errors
    receipt = responder.add_response(
        job.locator,
        uuid,
        job.dispute_txid,
        job.justice_txid,
        job.justice_rawtx,
        job.appointment_end,
        block_hash=get_random_value_hex(32),
    )

    assert receipt.delivered is True

    # The responder automatically fires create_job on adding a job if it is asleep. We need to stop the processes now.
    # To do so we delete all the jobs, stop the zmq and create a new fake block to unblock the queue.get method
    responder.jobs = dict()
    responder.zmq_subscriber.terminate = True
    responder.block_queue.put(get_random_value_hex(32))


def test_add_bad_response(responder):
    uuid = uuid4().hex
    job = create_dummy_job()

    # Now that the asleep / awake functionality has been tested we can avoid manually killing the responder by setting
    # to awake. That will prevent the zmq thread to be launched again.
    responder.asleep = False

    # A txid instead of a rawtx should be enough for unit tests using the bitcoind mock, better tests are needed though.
    job.justice_rawtx = job.justice_txid

    # The block_hash passed to add_response does not matter much now. It will in the future to deal with errors
    receipt = responder.add_response(
        job.locator,
        uuid,
        job.dispute_txid,
        job.justice_txid,
        job.justice_rawtx,
        job.appointment_end,
        block_hash=get_random_value_hex(32),
    )

    assert receipt.delivered is False


def test_create_job(responder):
    responder.asleep = False

    for _ in range(20):
        uuid = uuid4().hex
        confirmations = 0
        locator, dispute_txid, justice_txid, justice_rawtx, appointment_end = create_dummy_job_data(random_txid=True)

        # Check the job is not within the responder jobs before adding it
        assert uuid not in responder.jobs
        assert justice_txid not in responder.tx_job_map
        assert justice_txid not in responder.unconfirmed_txs

        # And that it is afterwards
        responder.create_job(uuid, locator, dispute_txid, justice_txid, justice_rawtx, appointment_end, confirmations)
        assert uuid in responder.jobs
        assert justice_txid in responder.tx_job_map
        assert justice_txid in responder.unconfirmed_txs

        # Check that the rest of job data also matches
        job = responder.jobs[uuid]
        assert (
            job.dispute_txid == dispute_txid
            and job.justice_txid == justice_txid
            and job.justice_rawtx == justice_rawtx
            and job.appointment_end == appointment_end
            and job.appointment_end == appointment_end
        )


def test_create_job_same_justice_txid(responder):
    # Create the same job using two different uuids
    confirmations = 0
    locator, dispute_txid, justice_txid, justice_rawtx, appointment_end = create_dummy_job_data(random_txid=True)
    uuid_1 = uuid4().hex
    uuid_2 = uuid4().hex

    responder.create_job(uuid_1, locator, dispute_txid, justice_txid, justice_rawtx, appointment_end, confirmations)
    responder.create_job(uuid_2, locator, dispute_txid, justice_txid, justice_rawtx, appointment_end, confirmations)

    # Check that both jobs have been added
    assert uuid_1 in responder.jobs and uuid_2 in responder.jobs
    assert justice_txid in responder.tx_job_map
    assert justice_txid in responder.unconfirmed_txs

    # Check that the rest of job data also matches
    for uuid in [uuid_1, uuid_2]:
        job = responder.jobs[uuid]
        assert (
            job.dispute_txid == dispute_txid
            and job.justice_txid == justice_txid
            and job.justice_rawtx == justice_rawtx
            and job.appointment_end == appointment_end
            and job.appointment_end == appointment_end
        )


def test_create_job_already_confirmed(responder):
    responder.asleep = False

    for i in range(20):
        uuid = uuid4().hex
        confirmations = i + 1
        locator, dispute_txid, justice_txid, justice_rawtx, appointment_end = create_dummy_job_data(
            justice_rawtx=TX.create_dummy_transaction()
        )

        responder.create_job(uuid, locator, dispute_txid, justice_txid, justice_rawtx, appointment_end, confirmations)

        assert justice_txid not in responder.unconfirmed_txs


def test_do_subscribe(responder):
    responder.block_queue = Queue()

    zmq_thread = Thread(target=responder.do_subscribe)
    zmq_thread.daemon = True
    zmq_thread.start()

    try:
        generate_block()
        block_hash = responder.block_queue.get()
        assert check_sha256_hex_format(block_hash)

    except Empty:
        assert False


def test_do_watch(temp_db_manager):
    responder = Responder(temp_db_manager)
    responder.block_queue = Queue()

    zmq_thread = Thread(target=responder.do_subscribe)
    zmq_thread.daemon = True
    zmq_thread.start()

    jobs = [create_dummy_job(justice_rawtx=TX.create_dummy_transaction()) for _ in range(20)]

    # Let's set up the jobs first
    for job in jobs:
        uuid = uuid4().hex

        responder.jobs[uuid] = job
        responder.tx_job_map[job.justice_txid] = [uuid]
        responder.missed_confirmations[job.justice_txid] = 0
        responder.unconfirmed_txs.append(job.justice_txid)

    # Let's start to watch
    watch_thread = Thread(target=responder.do_watch)
    watch_thread.daemon = True
    watch_thread.start()

    # And broadcast some of the transactions
    broadcast_txs = []
    for job in jobs[:5]:
        bitcoin_cli().sendrawtransaction(job.justice_rawtx)
        broadcast_txs.append(job.justice_txid)

    # Mine a block
    generate_block()

    # The transactions we sent shouldn't be in the unconfirmed transaction list anymore
    assert not set(broadcast_txs).issubset(responder.unconfirmed_txs)

    # TODO: test that reorgs can be detected once data persistence is merged (new version of the simulator)

    # Generating 5 additional blocks should complete the 5 jobs
    generate_blocks(5)

    assert not set(broadcast_txs).issubset(responder.tx_job_map)

    # Do the rest
    broadcast_txs = []
    for job in jobs[5:]:
        bitcoin_cli().sendrawtransaction(job.justice_rawtx)
        broadcast_txs.append(job.justice_txid)

    # Mine a block
    generate_blocks(6)

    assert len(responder.tx_job_map) == 0
    assert responder.asleep is True


def test_check_confirmations(temp_db_manager):
    responder = Responder(temp_db_manager)
    responder.block_queue = Queue()

    zmq_thread = Thread(target=responder.do_subscribe)
    zmq_thread.daemon = True
    zmq_thread.start()

    # check_confirmations checks, given a list of transaction for a block, what of the known justice transaction have
    # been confirmed. To test this we need to create a list of transactions and the state of the responder
    txs = [get_random_value_hex(32) for _ in range(20)]

    # The responder has a list of unconfirmed transaction, let make that some of them are the ones we've received
    responder.unconfirmed_txs = [get_random_value_hex(32) for _ in range(10)]
    txs_subset = random.sample(txs, k=10)
    responder.unconfirmed_txs.extend(txs_subset)

    # We also need to add them to the tx_job_map since they would be there in normal conditions
    responder.tx_job_map = {
        txid: Job(txid[:LOCATOR_LEN_HEX], txid, None, None, None) for txid in responder.unconfirmed_txs
    }

    # Let's make sure that there are no txs with missed confirmations yet
    assert len(responder.missed_confirmations) == 0

    responder.check_confirmations(txs)

    # After checking confirmations the txs in txs_subset should be confirmed (not part of unconfirmed_txs anymore)
    # and the rest should have a missing confirmation
    for tx in txs_subset:
        assert tx not in responder.unconfirmed_txs

    for tx in responder.unconfirmed_txs:
        assert responder.missed_confirmations[tx] == 1


def test_get_txs_to_rebroadcast(responder):
    # Let's create a few fake txids and assign at least 6 missing confirmations to each
    txs_missing_too_many_conf = {get_random_value_hex(32): 6 + i for i in range(10)}

    # Let's create some other transaction that has missed some confirmations but not that many
    txs_missing_some_conf = {get_random_value_hex(32): 3 for _ in range(10)}

    # All the txs in the first dict should be flagged as to_rebroadcast
    responder.missed_confirmations = txs_missing_too_many_conf
    txs_to_rebroadcast = responder.get_txs_to_rebroadcast(txs_missing_too_many_conf)
    assert txs_to_rebroadcast == list(txs_missing_too_many_conf.keys())

    # Non of the txs in the second dict should be flagged
    responder.missed_confirmations = txs_missing_some_conf
    txs_to_rebroadcast = responder.get_txs_to_rebroadcast(txs_missing_some_conf)
    assert txs_to_rebroadcast == []

    # Let's check that it also works with a mixed dict
    responder.missed_confirmations.update(txs_missing_too_many_conf)
    txs_to_rebroadcast = responder.get_txs_to_rebroadcast(txs_missing_some_conf)
    assert txs_to_rebroadcast == list(txs_missing_too_many_conf.keys())


def test_get_completed_jobs(db_manager):
    initial_height = bitcoin_cli().getblockcount()

    # Let's use a fresh responder for this to make it easier to compare the results
    responder = Responder(db_manager)

    # A complete job is a job that has reached the appointment end with enough confirmations (> MIN_CONFIRMATIONS)
    # We'll create three type of transactions: end reached + enough conf, end reached + no enough conf, end not reached
    jobs_end_conf = {uuid4().hex: create_dummy_job(justice_rawtx=TX.create_dummy_transaction()) for _ in range(10)}

    jobs_end_no_conf = {}
    for _ in range(10):
        job = create_dummy_job(justice_rawtx=TX.create_dummy_transaction())
        responder.unconfirmed_txs.append(job.justice_txid)
        jobs_end_no_conf[uuid4().hex] = job

    jobs_no_end = {}
    for _ in range(10):
        job = create_dummy_job(justice_rawtx=TX.create_dummy_transaction())
        job.appointment_end += 10
        jobs_no_end[uuid4().hex] = job

    # Let's add all to the  responder
    responder.jobs.update(jobs_end_conf)
    responder.jobs.update(jobs_end_no_conf)
    responder.jobs.update(jobs_no_end)

    for uuid, job in responder.jobs.items():
        bitcoin_cli().sendrawtransaction(job.justice_rawtx)

    # The dummy appointments have a end_appointment time of current + 2, but jobs need at least 6 confs by default
    generate_blocks(6)

    # And now let's check
    completed_jobs = responder.get_completed_jobs(initial_height + 6)
    completed_jobs_ids = [job_id for job_id, confirmations in completed_jobs]
    ended_jobs_keys = list(jobs_end_conf.keys())
    assert set(completed_jobs_ids) == set(ended_jobs_keys)

    # Generating 6 additional blocks should also confirm jobs_no_end
    generate_blocks(6)

    completed_jobs = responder.get_completed_jobs(initial_height + 12)
    completed_jobs_ids = [job_id for job_id, confirmations in completed_jobs]
    ended_jobs_keys.extend(list(jobs_no_end.keys()))

    assert set(completed_jobs_ids) == set(ended_jobs_keys)


def test_rebroadcast(db_manager):
    responder = Responder(db_manager)
    responder.asleep = False

    txs_to_rebroadcast = []

    # Rebroadcast calls add_response with retry=True. The job data is already in jobs.
    for i in range(20):
        uuid = uuid4().hex
        locator, dispute_txid, justice_txid, justice_rawtx, appointment_end = create_dummy_job_data(
            justice_rawtx=TX.create_dummy_transaction()
        )

        responder.jobs[uuid] = Job(locator, dispute_txid, justice_txid, justice_rawtx, appointment_end)
        responder.tx_job_map[justice_txid] = [uuid]
        responder.unconfirmed_txs.append(justice_txid)

        # Let's add some of the txs in the rebroadcast list
        if (i % 2) == 0:
            txs_to_rebroadcast.append(justice_txid)

    # The block_hash passed to rebroadcast does not matter much now. It will in the future to deal with errors
    receipts = responder.rebroadcast(txs_to_rebroadcast, get_random_value_hex(32))

    # All txs should have been delivered and the missed confirmation reset
    for txid, receipt in receipts:
        # Sanity check
        assert txid in txs_to_rebroadcast

        assert receipt.delivered is True
        assert responder.missed_confirmations[txid] == 0
