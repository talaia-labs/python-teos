import random
from uuid import uuid4

from pisa import c_logger
from pisa.responder import Job
from pisa.cleaner import Cleaner
from pisa.appointment import Appointment
from pisa.db_manager import WATCHER_PREFIX

from test.unit.conftest import get_random_value_hex

from common.constants import LOCATOR_LEN_BYTES, LOCATOR_LEN_HEX

CONFIRMATIONS = 6
ITEMS = 10
MAX_ITEMS = 100
ITERATIONS = 10

c_logger.disabled = True


# WIP: FIX CLEANER TESTS AFTER ADDING delete_complete_appointment
def set_up_appointments(db_manager, total_appointments):
    appointments = dict()
    locator_uuid_map = dict()

    for i in range(total_appointments):
        uuid = uuid4().hex
        locator = get_random_value_hex(LOCATOR_LEN_BYTES)

        appointment = Appointment(locator, None, None, None, None)
        appointments[uuid] = appointment
        locator_uuid_map[locator] = [uuid]

        db_manager.store_watcher_appointment(uuid, appointment.to_json())
        db_manager.store_update_locator_map(locator, uuid)

        # Each locator can have more than one uuid assigned to it.
        if i % 2:
            uuid = uuid4().hex

            appointments[uuid] = appointment
            locator_uuid_map[locator].append(uuid)

            db_manager.store_watcher_appointment(uuid, appointment.to_json())
            db_manager.store_update_locator_map(locator, uuid)

    return appointments, locator_uuid_map


def set_up_jobs(db_manager, total_jobs):
    jobs = dict()
    tx_job_map = dict()

    for i in range(total_jobs):
        uuid = uuid4().hex

        # We use the same txid for penalty and dispute here, it shouldn't matter
        penalty_txid = get_random_value_hex(32)
        dispute_txid = get_random_value_hex(32)
        locator = dispute_txid[:LOCATOR_LEN_HEX]

        # Assign both penalty_txid and dispute_txid the same id (it shouldn't matter)
        job = Job(locator, dispute_txid, penalty_txid, None, None)
        jobs[uuid] = job
        tx_job_map[penalty_txid] = [uuid]

        db_manager.store_responder_job(uuid, job.to_json())
        db_manager.store_update_locator_map(job.locator, uuid)

        # Each penalty_txid can have more than one uuid assigned to it.
        if i % 2:
            uuid = uuid4().hex

            jobs[uuid] = job
            tx_job_map[penalty_txid].append(uuid)

            db_manager.store_responder_job(uuid, job.to_json())
            db_manager.store_update_locator_map(job.locator, uuid)

    return jobs, tx_job_map


def test_delete_expired_appointment(db_manager):
    for _ in range(ITERATIONS):
        appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)
        expired_appointments = random.sample(list(appointments.keys()), k=ITEMS)

        Cleaner.delete_expired_appointment(expired_appointments, appointments, locator_uuid_map, db_manager)

        assert not set(expired_appointments).issubset(appointments.keys())


def test_delete_completed_appointments(db_manager):
    appointments, locator_uuid_map = set_up_appointments(db_manager, MAX_ITEMS)
    uuids = list(appointments.keys())

    for uuid in uuids:
        Cleaner.delete_completed_appointment(uuid, appointments, locator_uuid_map, db_manager)

    # All appointments should have been deleted
    assert len(appointments) == 0

    # Make sure that all appointments are flagged as triggered in the db
    db_appointments = db_manager.load_appointments_db(prefix=WATCHER_PREFIX)
    for uuid in uuids:
        assert db_appointments[uuid]["triggered"] is True


def test_delete_completed_jobs_db_match(db_manager):
    height = 0

    for _ in range(ITERATIONS):
        jobs, tx_job_map = set_up_jobs(db_manager, MAX_ITEMS)
        selected_jobs = random.sample(list(jobs.keys()), k=ITEMS)

        completed_jobs = [(job, 6) for job in selected_jobs]

        Cleaner.delete_completed_jobs(completed_jobs, height, jobs, tx_job_map, db_manager)

        assert not set(completed_jobs).issubset(jobs.keys())


def test_delete_completed_jobs_no_db_match(db_manager):
    height = 0

    for _ in range(ITERATIONS):
        jobs, tx_job_map = set_up_jobs(db_manager, MAX_ITEMS)
        selected_jobs = random.sample(list(jobs.keys()), k=ITEMS)

        # Let's change some uuid's by creating new jobs that are not included in the db and share a penalty_txid with
        # another job that is stored in the db.
        for uuid in selected_jobs[: ITEMS // 2]:
            penalty_txid = jobs[uuid].penalty_txid
            dispute_txid = get_random_value_hex(32)
            locator = dispute_txid[:LOCATOR_LEN_HEX]
            new_uuid = uuid4().hex

            jobs[new_uuid] = Job(locator, dispute_txid, penalty_txid, None, None)
            tx_job_map[penalty_txid].append(new_uuid)
            selected_jobs.append(new_uuid)

        # Let's add some random data
        for i in range(ITEMS // 2):
            uuid = uuid4().hex
            penalty_txid = get_random_value_hex(32)
            dispute_txid = get_random_value_hex(32)
            locator = dispute_txid[:LOCATOR_LEN_HEX]

            jobs[uuid] = Job(locator, dispute_txid, penalty_txid, None, None)
            tx_job_map[penalty_txid] = [uuid]
            selected_jobs.append(uuid)

        completed_jobs = [(job, 6) for job in selected_jobs]

        # We should be able to delete the correct ones and not fail in the others
        Cleaner.delete_completed_jobs(completed_jobs, height, jobs, tx_job_map, db_manager)
        assert not set(completed_jobs).issubset(jobs.keys())
