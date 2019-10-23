from pisa.logger import Logger

logger = Logger("Cleaner")

# Dictionaries in Python are "passed-by-reference", so no return is needed for the Cleaner"
# https://docs.python.org/3/faq/programming.html#how-do-i-write-a-function-with-output-parameters-call-by-reference


class Cleaner:
    @staticmethod
    def delete_expired_appointment(expired_appointments, appointments, locator_uuid_map, db_manager):
        for uuid in expired_appointments:
            locator = appointments[uuid].locator

            appointments.pop(uuid)

            if len(locator_uuid_map[locator]) == 1:
                locator_uuid_map.pop(locator)

            else:
                locator_uuid_map[locator].remove(uuid)

            logger.info("End time reached with no match. Deleting appointment.", locator=locator, uuid=uuid)

            # Delete appointment from the db
            db_manager.delete_watcher_appointment(uuid)

    @staticmethod
    def delete_completed_jobs(jobs, tx_job_map, completed_jobs, height, db_manager):
        for uuid, confirmations in completed_jobs:
            logger.info("Job completed. Appointment ended after reaching enough confirmations.",
                        uuid=uuid, height=height, confirmations=confirmations)

            # ToDo: #9-add-data-persistence
            justice_txid = jobs[uuid].justice_txid
            jobs.pop(uuid)

            if len(tx_job_map[justice_txid]) == 1:
                tx_job_map.pop(justice_txid)

                logger.info("No more jobs for justice transaction.", justice_txid=justice_txid)

            else:
                tx_job_map[justice_txid].remove(uuid)

            # Delete appointment from the db (both watchers's and responder's)
            db_manager.ddelete_watcher_appointment(uuid)
            db_manager.delete_responder_job(uuid)
