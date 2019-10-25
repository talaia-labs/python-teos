from pisa.responder import Job
from pisa.appointment import Appointment


class Builder:

    @staticmethod
    def build_appointments(appointments_data):
        appointments = {}
        locator_uuid_map = {}

        for uuid, appointment_data in appointments_data.items():
            appointment = Appointment.from_dict(appointment_data)
            appointments[uuid] = appointment

            if appointment.locator in locator_uuid_map:
                locator_uuid_map[appointment.locator].append(uuid)

            else:
                locator_uuid_map[appointment.locator] = [uuid]

        return appointments, locator_uuid_map

    @staticmethod
    def build_jobs(jobs_data):
        jobs = {}
        tx_job_map = {}

        for uuid, job_data in jobs_data.items():
            job = Job.from_dict(jobs_data)
            jobs[uuid] = job

            if job.justice_txid in tx_job_map:
                tx_job_map[job.justice_txid].append(uuid)

            else:
                tx_job_map[job.justice_txid] = [uuid]

        return jobs, tx_job_map
