from common.logger import Logger

logger = Logger("Cleaner")


class Cleaner:
    """
    The :class:`Cleaner` is the class in charge of removing expired/completed data from the tower.

    Mutable objects (like dicts) are passed-by-reference in Python, so no return is needed for the Cleaner.
    """

    @staticmethod
    def delete_appointment_from_memory(uuid, appointments, locator_uuid_map):
        """
        Deletes an appointment from memory (appointments and locator_uuid_map dictionaries). If the given appointment
        does not share locator with any other, the map will completely removed, otherwise, the uuid will be removed from
        the map.

        Args:
            uuid (:obj:`str`): the identifier of the appointment to be deleted.
            appointments (:obj:`dict`): the appointments dictionary from where the appointment should be removed.
            locator_uuid_map (:obj:`dict`): the locator:uuid map from where the appointment should also be removed.
        """
        locator = appointments[uuid].get("locator")

        # Delete the appointment
        appointments.pop(uuid)

        # If there was only one appointment that matches the locator we can delete the whole list
        if len(locator_uuid_map[locator]) == 1:
            locator_uuid_map.pop(locator)
        else:
            # Otherwise we just delete the appointment that matches locator:appointment_pos
            locator_uuid_map[locator].remove(uuid)

    @staticmethod
    def delete_appointment_from_db(uuid, db_manager):
        """
        Deletes an appointment from the appointments database.

        Args:
            uuid (:obj:`str`): the identifier of the appointment to be deleted.
            db_manager (:obj:`DBManager <pisa.db_manager.DBManager>`): a ``DBManager`` instance to interact with the
                database.
        """

        db_manager.delete_watcher_appointment(uuid)
        db_manager.delete_triggered_appointment_flag(uuid)

    @staticmethod
    def update_delete_db_locator_map(uuid, locator, db_manager):
        """
        Updates the locator:uuid map of a given locator from the database by removing a given uuid. If the uuid is the
        only element of the map, the map is deleted, otherwise the uuid is simply removed and the database is updated.

        If either the uuid of the locator are not found, the data is not modified.

        Args:
            uuid (:obj:`str`): the identifier to be removed from the map.
            locator (:obj:`str`): the identifier of the map to be either updated or deleted.
            db_manager (:obj:`DBManager <pisa.db_manager.DBManager>`): a ``DBManager`` instance to interact with the
                database.
        """

        locator_map = db_manager.load_locator_map(locator)
        if locator_map is not None:
            if uuid in locator_map:
                if len(locator_map) == 1:
                    db_manager.delete_locator_map(locator)
                else:
                    locator_map.remove(uuid)
                    db_manager.update_locator_map(locator, locator_map)
            else:
                logger.error("UUID not found in the db", uuid=uuid)
        else:
            logger.error("Locator not found in the db", uuid=uuid)

    @staticmethod
    def delete_expired_appointments(expired_appointments, appointments, locator_uuid_map, db_manager):
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
            locator = appointments[uuid].get("locator")
            logger.info("End time reached with no breach. Deleting appointment", locator=locator, uuid=uuid)

            Cleaner.delete_appointment_from_memory(uuid, appointments, locator_uuid_map)
            Cleaner.update_delete_db_locator_map(uuid, locator, db_manager)

            # Expired appointments are not flagged, so they can be deleted without caring about the db flag.
            db_manager.delete_watcher_appointment(uuid)

    @staticmethod
    def delete_completed_appointments(completed_appointments, appointments, locator_uuid_map, db_manager):
        """
        Deletes a completed appointment from memory (:obj:`Watcher <pisa.watcher.Watcher>`) and disk.

        Currently, an appointment is only completed if it cannot make it to the (:obj:`Responder <pisa.responder.Responder>`),
        otherwise, it will be flagged as triggered and removed once the tracker is completed.

        Args:
            completed_appointments (:obj:`list`): a list of appointments to be deleted.
            appointments (:obj:`dict`): a dictionary containing all the :obj:`Watcher <pisa.watcher.Watcher>`
                appointments.
            locator_uuid_map (:obj:`dict`): a ``locator:uuid`` map for the :obj:`Watcher <pisa.watcher.Watcher>`
                appointments.
            db_manager (:obj:`DBManager <pisa.db_manager.DBManager>`): a ``DBManager`` instance to interact with the
                database.
        """

        for uuid in completed_appointments:
            locator = appointments[uuid].get("locator")

            logger.warning(
                "Appointment cannot be completed, it contains invalid data. Deleting", locator=locator, uuid=uuid
            )

            Cleaner.delete_appointment_from_memory(uuid, appointments, locator_uuid_map)
            Cleaner.delete_appointment_from_db(uuid, db_manager)
            Cleaner.update_delete_db_locator_map(uuid, locator, db_manager)

    @staticmethod
    def flag_triggered_appointments(triggered_appointments, appointments, locator_uuid_map, db_manager):
        """
        Deletes a list of  triggered appointment from memory (:obj:`Watcher <pisa.watcher.Watcher>`) and flags them as
        triggered on disk.

        Args:
            triggered_appointments (:obj:`list`): a list of appointments to be flagged as triggered on the database.
            appointments (:obj:`dict`): a dictionary containing all the :obj:`Watcher <pisa.watcher.Watcher>`
                appointments.
            locator_uuid_map (:obj:`dict`): a ``locator:uuid`` map for the :obj:`Watcher <pisa.watcher.Watcher>`
                appointments.
            db_manager (:obj:`DBManager <pisa.db_manager.DBManager>`): a ``DBManager`` instance to interact with the
                database.
        """

        for uuid in triggered_appointments:
            Cleaner.delete_appointment_from_memory(uuid, appointments, locator_uuid_map)
            db_manager.create_triggered_appointment_flag(uuid)

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
                "Appointment completed. Appointment ended after reaching enough confirmations",
                uuid=uuid,
                height=height,
                confirmations=confirmations,
            )

            penalty_txid = trackers[uuid].get("penalty_txid")
            locator = trackers[uuid].get("locator")
            trackers.pop(uuid)

            if len(tx_tracker_map[penalty_txid]) == 1:
                tx_tracker_map.pop(penalty_txid)

                logger.info("No more trackers for penalty transaction", penalty_txid=penalty_txid)

            else:
                tx_tracker_map[penalty_txid].remove(uuid)

            # Delete appointment from the db (from watchers's and responder's db) and remove flag
            db_manager.delete_responder_tracker(uuid)
            Cleaner.delete_appointment_from_db(uuid, db_manager)

            # Update / delete the locator map
            Cleaner.update_delete_db_locator_map(uuid, locator, db_manager)
