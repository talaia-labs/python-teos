from queue import Queue

from pisa.responder import Job
from pisa.appointment import Appointment


class Builder:
    """
    The ``Builder`` class is in charge or reconstructing data loaded from the database and build the data structures
    of the :mod:`Watcher <pisa.watcher>` and the :mod:`Responder <pisa.responder>`.
    """

    @staticmethod
    def build_appointments(appointments_data):
        """
        Builds an appointments dictionary (``uuid: Appointment``) and a locator_uuid_map (``locator: uuid``) given a
        dictionary of appointments from the database.

        Args:
            appointments_data (dict): a dictionary of dictionaries representing all the :mod:`Watcher <pisa.watcher>`
                appointments stored in the database. The structure is as follows:

                    ``{uuid: {locator: str, start_time: int, ...}, uuid: {locator:...}}``

        Returns:
            ``tuple``: A tuple with two dictionaries. ``appointments`` containing the appointment information in
            :mod:`Appointment <pisa.appointment>` objects and ``locator_uuid_map`` containing a map of appointment
            (``uuid:locator``).
        """

        appointments = {}
        locator_uuid_map = {}

        for uuid, data in appointments_data.items():
            appointment = Appointment.from_dict(data)
            appointments[uuid] = appointment

            if appointment.locator in locator_uuid_map:
                locator_uuid_map[appointment.locator].append(uuid)

            else:
                locator_uuid_map[appointment.locator] = [uuid]

        return appointments, locator_uuid_map

    @staticmethod
    def build_jobs(jobs_data):
        """
        Builds a jobs dictionary (``uuid: Jobs``) and a tx_job_map (``penalty_txid: uuid``) given a dictionary of jobs
        from the database.

        Args:
            jobs_data (dict): a dictionary of dictionaries representing all the :mod:`Responder <pisa.responder>` jobs
                stored in the database. The structure is as follows:

                    ``{uuid: {locator: str, dispute_txid: str, ...}, uuid: {locator:...}}``

        Returns:
            ``tuple``: A tuple with two dictionaries. ``jobs`` containing the jobs information in
            :class:`Job <pisa.responder>` objects and a ``tx_job_map`` containing the map of jobs
            (``penalty_txid: uuid``).

        """

        jobs = {}
        tx_job_map = {}

        for uuid, data in jobs_data.items():
            job = Job.from_dict(data)
            jobs[uuid] = job

            if job.justice_txid in tx_job_map:
                tx_job_map[job.justice_txid].append(uuid)

            else:
                tx_job_map[job.justice_txid] = [uuid]

        return jobs, tx_job_map

    @staticmethod
    def build_block_queue(missed_blocks):
        """
        Builds a ``Queue`` of block hashes to initialize the :mod:`Watcher <pisa.watcher>` or the
        :mod:`Responder <pisa.responder>` using backed up data.

        Args:
            missed_blocks (list): list of block hashes missed by the Watchtower (do to a crash or shutdown).

        Returns:
            ``Queue``: A `Queue` containing all the missed blocks hashes.
        """

        block_queue = Queue()

        for block in missed_blocks:
            block_queue.put(block)

        return block_queue
