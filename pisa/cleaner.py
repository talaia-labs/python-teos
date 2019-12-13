from pisa.logger import Logger

logger = Logger("Cleaner")


class Cleaner:
    """
    The :class:`Cleaner` is the class in charge of removing expired/completed data from the tower.

    Mutable objects (like dicts) are passed-by-reference in Python, so no return is needed for the Cleaner.
    """

    @staticmethod
    def delete_expired_appointment(expired_appointments, appointments, locator_uuid_map, db_manager):
        """
        Deletes appointments which ``end_time`` has been reached (with no trigger) both from memory
        (:obj:`Watcher <pisa.watcher.Watcher>`) and disk.

        Args:
            expired_appointments (:obj:`list`): a list of appointments to be deleted.
            appointments (:obj:`dict`): a dictionary containing all the :mod:`Watcher <pisa.watcher.Watcher>`
                appointments.
            locator_uuid_map (:obj:`dict`): a ``locator:uuid`` map for the :obj:`Watcher <pisa.watcher.Watcher>`
                appointments.
            db_manager (:obj:`DBManager <pisa.db_manager.DBManager>`): a ``DBManager`` instance to interact with the
                database.
        """

        for uuid in expired_appointments:
            locator = appointments[uuid].locator

            appointments.pop(uuid)

            if len(locator_uuid_map[locator]) == 1:
                locator_uuid_map.pop(locator)

            else:
                locator_uuid_map[locator].remove(uuid)

            logger.info("End time reached with no breach. Deleting appointment.", locator=locator, uuid=uuid)

            # Delete appointment from the db
            db_manager.delete_watcher_appointment(uuid)

    @staticmethod
    def delete_completed_appointment(uuid, appointments, locator_uuid_map, db_manager):
        """
        Deletes a triggered appointment from memory (:obj:`Watcher <pisa.watcher.Watcher>`) and flags it as triggered in
        disk.

        Args:
            uuid (:obj:`str`): a unique 16-byte hex-encoded str that identifies the appointment.
            appointments (:obj:`dict`): a dictionary containing all the :obj:`Watcher <pisa.watcher.Watcher>`
                appointments.
            locator_uuid_map (:obj:`dict`): a ``locator:uuid`` map for the :obj:`Watcher <pisa.watcher.Watcher>`
                appointments.
            db_manager (:obj:`DBManager <pisa.db_manager.DBManager>`): a ``DBManager`` instance to interact with the
                database.
        """

        # Delete the appointment
        appointment = appointments.pop(uuid)

        # If there was only one appointment that matches the locator we can delete the whole list
        if len(locator_uuid_map[appointment.locator]) == 1:
            locator_uuid_map.pop(appointment.locator)
        else:
            # Otherwise we just delete the appointment that matches locator:appointment_pos
            locator_uuid_map[appointment.locator].remove(uuid)

        # DISCUSS: instead of deleting the appointment, we will mark it as triggered and delete it from both
        #          the watcher's and responder's db after fulfilled
        # Update appointment in the db
        db_manager.store_watcher_appointment(uuid, appointment.to_json(triggered=True))

    @staticmethod
    def delete_completed_trackers(completed_trackers, height, trackers, tx_tracker_map, db_manager):
        """
        Deletes a completed tracker both from memory (:obj:`Responder <pisa.responder.Responder>`) and disk (from the
        Responder's and Watcher's databases).

        Args:
            trackers (:obj:`dict`): a dictionary containing all the :obj:`Responder <pisa.responder.Responder>`
                trackers.
            tx_tracker_map (:obj:`dict`): a ``penalty_txid:uuid`` map for the :obj:`Responder
                <pisa.responder.Responder>` trackers.
            completed_trackers (:obj:`list`): a list of completed trackers to be deleted.
            height (:obj:`int`): the block height at which the trackers were completed.
            db_manager (:obj:`DBManager <pisa.db_manager.DBManager>`): a ``DBManager`` instance to interact with the
                database.
        """

        for uuid, confirmations in completed_trackers:
            logger.info(
                "Appointment completed. Appointment ended after reaching enough confirmations.",
                uuid=uuid,
                height=height,
                confirmations=confirmations,
            )

            penalty_txid = trackers[uuid].penalty_txid
            locator = trackers[uuid].locator
            trackers.pop(uuid)

            if len(tx_tracker_map[penalty_txid]) == 1:
                tx_tracker_map.pop(penalty_txid)

                logger.info("No more trackers for penalty transaction.", penalty_txid=penalty_txid)

            else:
                tx_tracker_map[penalty_txid].remove(uuid)

            # Delete appointment from the db (both watchers's and responder's)
            db_manager.delete_watcher_appointment(uuid)
            db_manager.delete_responder_tracker(uuid)

            # Update / delete the locator map
            locator_map = db_manager.load_locator_map(locator)
            if locator_map is not None:
                if uuid in locator_map:
                    if len(locator_map) == 1:
                        db_manager.delete_locator_map(locator)

                    else:
                        locator_map.remove(uuid)
                        db_manager.store_update_locator_map(locator, locator_map)

                else:
                    logger.error("UUID not found in the db.", uuid=uuid)

            else:
                logger.error("Locator not found in the db.", uuid=uuid)
