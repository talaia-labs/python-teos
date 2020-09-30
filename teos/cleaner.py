from teos.logger import get_logger


class Cleaner:
    """
    The :class:`Cleaner` is in charge of removing outdated/completed data from the tower.

    Mutable objects (like dicts) are passed-by-reference in Python, so no return is needed for the Cleaner.
    """

    logger = get_logger(component="Cleaner")

    @staticmethod
    def delete_appointment_from_memory(uuid, appointments, locator_uuid_map):
        """
        Deletes an appointment from memory (``appointments`` and ``locator_uuid_map`` dictionaries). If the given
        appointment does not share locator with any other, the map will completely removed, otherwise, the uuid will be
        removed from the map.

        Args:
            uuid (:obj:`str`): the identifier of the appointment to be deleted.
            appointments (:obj:`dict`): the appointments dictionary from where the appointment should be removed.
            locator_uuid_map (:obj:`dict`): the ``locator:uuid`` map from where the appointment should also be removed.
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
            db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): an instance of the appointment
                database manager to interact with the database.
        """

        db_manager.delete_watcher_appointment(uuid)
        db_manager.delete_triggered_appointment_flag(uuid)

    @staticmethod
    def update_delete_db_locator_map(uuids, locator, db_manager):
        """
        Updates the ``locator:uuid`` map of a given locator from the database by removing a given uuid. If the uuid is
        the only element of the map, the map is deleted, otherwise the uuid is simply removed and the database is
        updated.

        If either the uuid of the locator are not found, the data is not modified.

        Args:
            uuids (:obj:`list`): a list of identifiers to be removed from the map.
            locator (:obj:`str`): the identifier of the map to be either updated or deleted.
            db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): an instance of the appointment
                database manager to interact with the database.
        """

        locator_map = db_manager.load_locator_map(locator)

        if locator_map is not None:
            if set(locator_map).issuperset(uuids):
                # Remove the map if all keys are requested to be deleted
                if set(locator_map) == set(uuids):
                    db_manager.delete_locator_map(locator)
                else:
                    # Otherwise remove only the selected keys
                    locator_map = list(set(locator_map).difference(uuids))
                    db_manager.update_locator_map(locator, locator_map)

            else:
                Cleaner.logger.error("Some UUIDs not found in the db", locator=locator, all_uuids=uuids)

        else:
            Cleaner.logger.error("Locator map not found in the db", locator=locator)

    @staticmethod
    def delete_outdated_appointments(outdated_appointments, appointments, locator_uuid_map, db_manager):
        """
        Deletes appointments that have outdated (with no trigger) both from memory
        (:obj:`Watcher <teos.watcher.Watcher>`) and disk.

        Args:
            outdated_appointments (:obj:`list`): a list of appointments to be deleted.
            appointments (:obj:`dict`): a dictionary containing all the :mod:`Watcher <teos.watcher.Watcher>`
                appointments.
            locator_uuid_map (:obj:`dict`): a ``locator:uuid`` map for the :obj:`Watcher <teos.watcher.Watcher>`
                appointments.
            db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): an instance of the appointment
                database manager to interact with the database.
        """

        locator_maps_to_update = {}

        for uuid in outdated_appointments:
            locator = appointments[uuid].get("locator")
            Cleaner.logger.info("End time reached with no breach. Deleting appointment", locator=locator, uuid=uuid)

            Cleaner.delete_appointment_from_memory(uuid, appointments, locator_uuid_map)

            if locator not in locator_maps_to_update:
                locator_maps_to_update[locator] = []

            locator_maps_to_update[locator].append(uuid)

        for locator, uuids in locator_maps_to_update.items():
            Cleaner.update_delete_db_locator_map(uuids, locator, db_manager)

        # Outdated appointments are not flagged, so they can be deleted without caring about the db flag.
        db_manager.batch_delete_watcher_appointments(outdated_appointments)

    @staticmethod
    def delete_completed_appointments(completed_appointments, appointments, locator_uuid_map, db_manager):
        """
        Deletes a completed appointment from memory (:obj:`Watcher <teos.watcher.Watcher>`) and disk.

        Currently, an appointment is only completed if it cannot make it to the
        (:obj:`Responder <teos.responder.Responder>`), otherwise, it will be flagged as triggered and removed once the
        tracker is completed.

        Args:
            completed_appointments (:obj:`list`): a list of appointments to be deleted.
            appointments (:obj:`dict`): a dictionary containing all the :obj:`Watcher <teos.watcher.Watcher>`
                appointments.
            locator_uuid_map (:obj:`dict`): a ``locator:uuid`` map for the :obj:`Watcher <teos.watcher.Watcher>`
                appointments.
            db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): an instance of the appointment
                database manager to interact with the database.
        """

        locator_maps_to_update = {}

        for uuid in completed_appointments:
            locator = appointments[uuid].get("locator")

            Cleaner.logger.warning(
                "Appointment cannot be completed, it contains invalid data. Deleting", locator=locator, uuid=uuid
            )

            Cleaner.delete_appointment_from_memory(uuid, appointments, locator_uuid_map)

            if locator not in locator_maps_to_update:
                locator_maps_to_update[locator] = []

            locator_maps_to_update[locator].append(uuid)

        for locator, uuids in locator_maps_to_update.items():
            # Update / delete the locator map
            Cleaner.update_delete_db_locator_map(uuids, locator, db_manager)

        db_manager.batch_delete_watcher_appointments(completed_appointments)

    @staticmethod
    def flag_triggered_appointments(triggered_appointments, appointments, locator_uuid_map, db_manager):
        """
        Deletes a list of triggered appointment from memory (:obj:`Watcher <teos.watcher.Watcher>`) and flags them as
        triggered on disk.

        Args:
            triggered_appointments (:obj:`list`): a list of appointments to be flagged as triggered on the database.
            appointments (:obj:`dict`): a dictionary containing all the :obj:`Watcher <teos.watcher.Watcher>`
                appointments.
            locator_uuid_map (:obj:`dict`): a ``locator:uuid`` map for the :obj:`Watcher <teos.watcher.Watcher>`
                appointments.
            db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): an instance of the appointment
                database manager to interact with the database.
        """

        for uuid in triggered_appointments:
            Cleaner.delete_appointment_from_memory(uuid, appointments, locator_uuid_map)
            db_manager.create_triggered_appointment_flag(uuid)

    @staticmethod
    def delete_trackers(completed_trackers, height, trackers, tx_tracker_map, db_manager, outdated=False):
        """
        Deletes completed/outdated trackers both from memory (:obj:`Responder <teos.responder.Responder>`) and disk
        (from the :obj:`Responder`'s and :obj:`Watcher`'s databases).

        Args:
            trackers (:obj:`dict`): a dictionary containing all the :obj:`Responder <teos.responder.Responder>`
                trackers.
            height (:obj:`int`): the block height at which the trackers were completed.
            tx_tracker_map (:obj:`dict`): a ``penalty_txid:uuid`` map for the :obj:`Responder
                <teos.responder.Responder>` trackers.
            completed_trackers (:obj:`dict`): a dict of completed/outdated trackers to be deleted
                (``uuid:confirmations``).
            db_manager (:obj:`AppointmentsDBM <teos.appointments_dbm.AppointmentsDBM>`): an instance of the appointment
                database manager to interact with the database.
            outdated (:obj:`bool`): whether the trackers have been outdated or not. Defaults to False.
        """

        locator_maps_to_update = {}

        for uuid in completed_trackers:

            if outdated:
                Cleaner.logger.info(
                    "Appointment couldn't be completed. Expiry reached but penalty didn't make it to the chain",
                    uuid=uuid,
                    height=height,
                )
            else:
                Cleaner.logger.info(
                    "Appointment completed. Penalty transaction was irrevocably confirmed", uuid=uuid, height=height
                )

            penalty_txid = trackers[uuid].get("penalty_txid")
            locator = trackers[uuid].get("locator")
            trackers.pop(uuid)

            if len(tx_tracker_map[penalty_txid]) == 1:
                tx_tracker_map.pop(penalty_txid)

                Cleaner.logger.info("No more trackers for penalty transaction", penalty_txid=penalty_txid)

            else:
                tx_tracker_map[penalty_txid].remove(uuid)

            if locator not in locator_maps_to_update:
                locator_maps_to_update[locator] = []

            locator_maps_to_update[locator].append(uuid)

        for locator, uuids in locator_maps_to_update.items():
            # Update / delete the locator map
            Cleaner.update_delete_db_locator_map(uuids, locator, db_manager)

        # Delete appointment from the db (from watcher's and responder's db) and remove flag
        db_manager.batch_delete_responder_trackers(completed_trackers)
        db_manager.batch_delete_watcher_appointments(completed_trackers)
        db_manager.batch_delete_triggered_appointment_flag(completed_trackers)

    @staticmethod
    def delete_gatekeeper_appointments(appointment_to_delete, registered_users, user_db):
        """
        Deletes a list of outdated / completed appointments of a given user both from memory and the UserDB.

        Args:
            appointment_to_delete (:obj:`dict`): ``uuid:user_id`` dict containing the appointments to delete
                (outdated + completed)
            registered_users (:obj:`dict`): a dictionary of registered users from the gatekeeper.
            user_db (:obj:`UsersDBM <teos.user_dbm.UsersDBM>`): A user database manager instance to interact with the
            database.
        """

        user_ids = []
        # Remove appointments from memory
        for uuid, user_id in appointment_to_delete.items():
            if user_id in registered_users and uuid in registered_users[user_id].appointments:
                # Remove the appointment from the appointment list and update the available slots
                freed_slots = registered_users[user_id].appointments.pop(uuid)
                registered_users[user_id].available_slots += freed_slots

                if user_id not in user_ids:
                    user_ids.append(user_id)

        # Store the updated users in the DB
        for user_id in user_ids:
            user_db.store_user(user_id, registered_users[user_id].to_dict())

    @staticmethod
    def delete_outdated_users(outdated_users, registered_users, user_db):
        """
        Deletes users whose subscription has been outdated, alongside all their associated data (appointments and
        trackers).

        Args:
            outdated_users (:obj:`list): a list of user_ids to be deleted.
            registered_users (:obj:`dict`): a dictionary of registered users from the gatekeeper.
            user_db (:obj:`UsersDBM <teos.user_dbm.UsersDBM>`): A user database manager instance to interact with the
            database.
        """

        for user_id in outdated_users:
            registered_users.pop(user_id)
            user_db.delete_user(user_id)
