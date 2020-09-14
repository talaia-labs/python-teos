from teos.responder import TransactionTracker
from teos.extended_appointment import ExtendedAppointment


class Builder:
    """
    The :class:`Builder` class is in charge of reconstructing data loaded from the appointments database and build the
    data structures of the :obj:`Watcher <teos.watcher.Watcher>` and the :obj:`Responder <teos.responder.Responder>`.
    """

    @staticmethod
    def build_appointments(appointments_data):
        """
        Builds an appointments dictionary (``uuid:extended_appointment``) and a locator_uuid_map (``locator:uuid``)
        given a dictionary of appointments from the database.

        Args:
            appointments_data (:obj:`dict`): a dictionary of dictionaries representing all the
                :obj:`Watcher <teos.watcher.Watcher>` appointments stored in the database. The structure is as follows:

                    ``{uuid: {locator: str, ...}, uuid: {locator:...}}``

        Returns:
            :obj:`tuple`: A tuple with two dictionaries. ``appointments`` containing the appointment information in
            :obj:`ExtendedAppointment <teos.extended_appointment.ExtendedAppointment>` objects and ``locator_uuid_map``
            containing a map of appointment (``uuid:locator``).
        """

        appointments = {}
        locator_uuid_map = {}

        for uuid, data in appointments_data.items():
            ext_appointment = ExtendedAppointment.from_dict(data)
            appointments[uuid] = ext_appointment.get_summary()

            if ext_appointment.locator in locator_uuid_map:
                locator_uuid_map[ext_appointment.locator].append(uuid)

            else:
                locator_uuid_map[ext_appointment.locator] = [uuid]

        return appointments, locator_uuid_map

    @staticmethod
    def build_trackers(tracker_data):
        """
        Builds a tracker dictionary (``uuid:TransactionTracker``) and a tx_tracker_map (``penalty_txid:uuid``) given
        a dictionary of trackers from the database.

        Args:
            tracker_data (:obj:`dict`): a dictionary of dictionaries representing all the
                :mod:`Responder <teos.responder.Responder>` trackers stored in the database.
                The structure is as follows:

                    ``{uuid: {locator: str, dispute_txid: str, ...}, uuid: {locator:...}}``

        Returns:
            :obj:`tuple`: A tuple with two dictionaries. ``trackers`` containing the trackers' information in
            :obj:`TransactionTracker <teos.responder.TransactionTracker>` objects and a ``tx_tracker_map`` containing
            the map of trackers (``penalty_txid: uuid``).

        """

        trackers = {}
        tx_tracker_map = {}

        for uuid, data in tracker_data.items():
            tracker = TransactionTracker.from_dict(data)
            trackers[uuid] = tracker.get_summary()

            if tracker.penalty_txid in tx_tracker_map:
                tx_tracker_map[tracker.penalty_txid].append(uuid)

            else:
                tx_tracker_map[tracker.penalty_txid] = [uuid]

        return trackers, tx_tracker_map

    @staticmethod
    def populate_block_queue(block_queue, missed_blocks):
        """
        Populates a ``Queue`` of block hashes to initialize the :mod:`Watcher <teos.watcher.Watcher>` or the
        :mod:`Responder <teos.responder.Responder>` using backed up data.

        Args:
            block_queue (:obj:`Queue`): a queue.
            missed_blocks (:obj:`list`): list of block hashes missed by the Watchtower (due to a crash or shutdown).

        Returns:
            :obj:`Queue`: A queue containing all the missed blocks hashes.
        """

        for block in missed_blocks:
            block_queue.put(block)

    @staticmethod
    def update_states(watcher, missed_blocks_watcher, missed_blocks_responder):
        """
        Updates the states of both the :mod:`Watcher <teos.watcher.Watcher>` and the
        :mod:`Responder <teos.responder.Responder>`. If both have pending blocks to process they need to be updated at
        the same time, block by block.

        If only one instance has to be updated, ``populate_block_queue`` should be used.

        Args:
            watcher (:obj:`Watcher <teos.watcher.Watcher>`): a :obj:`Watcher` instance (including a :obj:`Responder`).
            missed_blocks_watcher (:obj:`list`): the list of block missed by the :obj:`Watcher`.
            missed_blocks_responder (:obj:`list`): the list of block missed by the :obj:`Responder`.

        Raises:
            ValueError: if one of the provided list is empty.
        """

        if len(missed_blocks_responder) == 0 or len(missed_blocks_watcher) == 0:
            raise ValueError(
                "Both the Watcher and the Responder must have missed blocks. Use ``populate_block_queue`` otherwise."
            )

        # If the missed blocks of the Watcher and the Responder are not the same, we need to bring one up to date with
        # the other.
        if len(missed_blocks_responder) > len(missed_blocks_watcher):
            block_diff = sorted(
                set(missed_blocks_responder).difference(missed_blocks_watcher), key=missed_blocks_responder.index
            )
            Builder.populate_block_queue(watcher.responder.block_queue, block_diff)
            watcher.responder.block_queue.join()

        elif len(missed_blocks_watcher) > len(missed_blocks_responder):
            block_diff = sorted(
                set(missed_blocks_watcher).difference(missed_blocks_responder), key=missed_blocks_watcher.index
            )
            Builder.populate_block_queue(watcher.block_queue, block_diff)
            watcher.block_queue.join()

        # Once they are at the same height, we update them one by one
        for block in missed_blocks_watcher:
            watcher.block_queue.put(block)
            watcher.block_queue.join()

            watcher.responder.block_queue.put(block)
            watcher.responder.block_queue.join()
