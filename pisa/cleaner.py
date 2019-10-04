import pisa.conf as conf
from pisa import logging


class Cleaner:
    @staticmethod
    def delete_expired_appointment(block, appointments, locator_uuid_map):
        to_delete = [uuid for uuid, appointment in appointments.items()
                     if block["height"] > appointment.end_time + conf.EXPIRY_DELTA]

        for uuid in to_delete:
            locator = appointments[uuid].locator

            appointments.pop(uuid)

            if len(locator_uuid_map[locator]) == 1:
                locator_uuid_map.pop(locator)

            else:
                locator_uuid_map[locator].remove(uuid)

            logging.info("[Cleaner] end time reached with no match! Deleting appointment {} (uuid: {})".format(locator,
                                                                                                               uuid))

        return appointments, locator_uuid_map

    @staticmethod
    def delete_completed_jobs(jobs, tx_job_map, completed_jobs, height):
        for uuid in completed_jobs:
            logging.info("[Cleaner] job completed (uuid = {}). Appointment ended at block {} after {} confirmations"
                         .format(uuid, jobs[uuid].justice_txid, height, jobs[uuid].confirmations))

            # ToDo: #9-add-data-persistence
            justice_txid = jobs[uuid].justice_txid
            jobs.pop(uuid)

            if len(tx_job_map[justice_txid]) == 1:
                tx_job_map.pop(justice_txid)

                logging.info("[Cleaner] no more jobs for justice_txid {}".format(justice_txid))

            else:
                tx_job_map[justice_txid].remove(uuid)

        return jobs, tx_job_map
