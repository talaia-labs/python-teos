from pisa import logging

# Dictionaries in Python are "passed-by-reference", so no return is needed for the Cleaner"
# https://docs.python.org/3/faq/programming.html#how-do-i-write-a-function-with-output-parameters-call-by-reference


class Cleaner:
    @staticmethod
    def delete_expired_appointment(expired_appointments, appointments, locator_uuid_map):
        for uuid in expired_appointments:
            locator = appointments[uuid].locator

            appointments.pop(uuid)

            if len(locator_uuid_map[locator]) == 1:
                locator_uuid_map.pop(locator)

            else:
                locator_uuid_map[locator].remove(uuid)

            logging.info("[Cleaner] end time reached with no match! Deleting appointment {} (uuid: {})".format(locator,
                                                                                                               uuid))

    @staticmethod
    def delete_completed_jobs(jobs, tx_job_map, completed_jobs, height):
        for uuid, confirmations in completed_jobs:
            logging.info("[Cleaner] job completed (uuid = {}). Appointment ended at block {} after {} confirmations"
                         .format(uuid, height, confirmations))

            # ToDo: #9-add-data-persistence
            justice_txid = jobs[uuid].justice_txid
            jobs.pop(uuid)

            if len(tx_job_map[justice_txid]) == 1:
                tx_job_map.pop(justice_txid)

                logging.info("[Cleaner] no more jobs for justice_txid {}".format(justice_txid))

            else:
                tx_job_map[justice_txid].remove(uuid)
