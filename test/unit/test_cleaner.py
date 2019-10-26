import random
from uuid import uuid4

from pisa import logging
from pisa.responder import Job
from pisa.cleaner import Cleaner
from pisa.appointment import Appointment
from test.unit.conftest import get_random_value_hex

CONFIRMATIONS = 6
ITEMS = 10
MAX_ITEMS = 100
ITERATIONS = 1000

logging.getLogger().disabled = True


def set_up_appointments(total_appointments):
    appointments = dict()
    locator_uuid_map = dict()

    for _ in range(total_appointments):
        uuid = uuid4().hex
        locator = get_random_value_hex(32)

        appointments[uuid] = Appointment(locator, None, None, None, None, None, None)
        locator_uuid_map[locator] = [uuid]

        # Each locator can have more than one uuid assigned to it. Do a coin toss to add multiple ones
        while random.randint(0, 1):
            uuid = uuid4().hex

            appointments[uuid] = Appointment(locator, None, None, None, None, None, None)
            locator_uuid_map[locator].append(uuid)

    return appointments, locator_uuid_map


def set_up_jobs(total_jobs):
    jobs = dict()
    tx_job_map = dict()

    for _ in range(total_jobs):
        uuid = uuid4().hex
        txid = get_random_value_hex(32)

        # Assign both justice_txid and dispute_txid the same id (it shouldn't matter)
        jobs[uuid] = Job(txid, txid, None, None)
        tx_job_map[txid] = [uuid]

        # Each justice_txid can have more than one uuid assigned to it. Do a coin toss to add multiple ones
        while random.randint(0, 1):
            uuid = uuid4().hex

            jobs[uuid] = Job(txid, txid, None, None)
            tx_job_map[txid].append(uuid)

    return jobs, tx_job_map


def test_delete_expired_appointment(db_manager):

    for _ in range(ITERATIONS):
        appointments, locator_uuid_map = set_up_appointments(MAX_ITEMS)
        expired_appointments = random.sample(list(appointments.keys()), k=ITEMS)

        Cleaner.delete_expired_appointment(expired_appointments, appointments, locator_uuid_map, db_manager)

        assert not set(expired_appointments).issubset(appointments.keys())


def test_delete_completed_jobs(db_manager):
    height = 0

    for _ in range(ITERATIONS):
        jobs, tx_job_map = set_up_jobs(MAX_ITEMS)
        selected_jobs = random.sample(list(jobs.keys()), k=ITEMS)

        completed_jobs = [(job, 6) for job in selected_jobs]

        Cleaner.delete_completed_jobs(jobs, tx_job_map, completed_jobs, height, db_manager)

        assert not set(completed_jobs).issubset(jobs.keys())
