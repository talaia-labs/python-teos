from uuid import uuid4

from pisa.builder import Builder
from test.unit.conftest import get_random_value_hex
from test.unit.test_api import generate_dummy_appointment


def generate_dummy_job():
    dispute_txid = get_random_value_hex(32)
    justice_txid = get_random_value_hex(32)
    justice_rawtx = get_random_value_hex(100)

    return {"dispute_txid": dispute_txid, "justice_txid": justice_txid, "justice_rawtx": justice_rawtx,
            "appointment_end": 100}


def test_build_appointments(run_bitcoind):
    appointments_data = {}

    # Create some appointment data
    for i in range(10):
        data, _ = generate_dummy_appointment()
        uuid = uuid4().hex

        appointments_data[uuid] = data

        # Add some additional appointments that share the same locator to test all the builder's cases
        if i % 2 == 0:
            locator = data["locator"]
            data, _ = generate_dummy_appointment()
            uuid = uuid4().hex
            data["locator"] = locator

            appointments_data[uuid] = data

    # Use the builder to create the data structures
    appointments, locator_uuid_map = Builder.build_appointments(appointments_data)

    # Check that the created appointments match the data
    for uuid, appointment in appointments.items():
        assert uuid in appointments_data.keys()
        assert appointments_data[uuid] == appointment.to_dict()
        assert uuid in locator_uuid_map[appointment.locator]


def test_build_jobs():
    jobs_data = {}

    # Create some jobs data
    for i in range(10):
        data = generate_dummy_job()

        jobs_data[uuid4().hex] = data

        # Add some additional jobs that share the same locator to test all the builder's cases
        if i % 2 == 0:
            justice_txid = data["justice_txid"]
            data = generate_dummy_job()
            data["justice_txid"] = justice_txid

            jobs_data[uuid4().hex] = data

    jobs, tx_job_map = Builder.build_jobs(jobs_data)

    # Check that the built jobs match the data
    for uuid, job in jobs.items():
        assert uuid in jobs_data.keys()
        job_dict = job.to_dict()

        # The locator is not part of the job_data found in the database (for now)
        job_dict.pop('locator')
        assert jobs_data[uuid] == job_dict
        assert uuid in tx_job_map[job.justice_txid]


def test_build_block_queue():
    # Create some random block hashes and construct the queue with them
    blocks = [get_random_value_hex(32) for _ in range(10)]
    queue = Builder.build_block_queue(blocks)

    # Make sure every block is in the queue and that there are not additional ones
    while not queue.empty():
        block = queue.get()
        assert block in blocks
        blocks.remove(block)

    assert len(blocks) == 0



