import random
from uuid import uuid4

from pisa import c_logger
from pisa.responder import Job
from pisa.cleaner import Cleaner
from pisa.appointment import Appointment
from pisa.db_manager import WATCHER_PREFIX
from test.unit.conftest import get_random_value_hex

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
        locator = get_random_value_hex(32)

        appointment = Appointment(locator, None, None, None, None, None)
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

        # We use the same txid for justice and dispute here, it shouldn't matter
        justice_txid = get_random_value_hex(32)
        dispute_txid = get_random_value_hex(32)

        # Assign both justice_txid and dispute_txid the same id (it shouldn't matter)
        job = Job(dispute_txid, justice_txid, None, None)
        jobs[uuid] = job
        tx_job_map[justice_txid] = [uuid]

        db_manager.store_responder_job(uuid, job.to_json())
        db_manager.store_update_locator_map(job.locator, uuid)

        # Each justice_txid can have more than one uuid assigned to it.
        if i % 2:
            uuid = uuid4().hex

            jobs[uuid] = job
            tx_job_map[justice_txid].append(uuid)

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
        Cleaner.delete_completed_appointment(
            appointments[uuid].locator, uuid, appointments, locator_uuid_map, db_manager
        )

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

        Cleaner.delete_completed_jobs(jobs, tx_job_map, completed_jobs, height, db_manager)

        assert not set(completed_jobs).issubset(jobs.keys())


def test_delete_completed_jobs_no_db_match(db_manager):
    height = 0

    for _ in range(ITERATIONS):
        jobs, tx_job_map = set_up_jobs(db_manager, MAX_ITEMS)
        selected_jobs = random.sample(list(jobs.keys()), k=ITEMS)

        # Let's change some uuid's by creating new jobs that are not included in the db and share a justice_txid with
        # another job that is stored in the db.
        for uuid in selected_jobs[: ITEMS // 2]:
            justice_txid = jobs[uuid].justice_txid
            dispute_txid = get_random_value_hex(32)
            new_uuid = uuid4().hex

            jobs[new_uuid] = Job(dispute_txid, justice_txid, None, None)
            tx_job_map[justice_txid].append(new_uuid)
            selected_jobs.append(new_uuid)

        # Let's add some random data
        for i in range(ITEMS // 2):
            uuid = uuid4().hex
            justice_txid = get_random_value_hex(32)
            dispute_txid = get_random_value_hex(32)

            jobs[uuid] = Job(dispute_txid, justice_txid, None, None)
            tx_job_map[justice_txid] = [uuid]
            selected_jobs.append(uuid)

        completed_jobs = [(job, 6) for job in selected_jobs]

        # We should be able to delete the correct ones and not fail in the others
        Cleaner.delete_completed_jobs(jobs, tx_job_map, completed_jobs, height, db_manager)
        assert not set(completed_jobs).issubset(jobs.keys())
