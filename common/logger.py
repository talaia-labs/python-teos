import json
import logging
from datetime import datetime


class _StructuredMessage:
    def __init__(self, message, **kwargs):
        self.message = message
        self.time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.kwargs = kwargs

    def to_dict(self):
        return {**self.kwargs, "message": self.message, "time": self.time}


class Logger:
    """
    The :class:`Logger` is the class in charge of logging events into the log file.

    Args:
        actor (:obj:`str`): the system actor that is logging the event (e.g. ``Watcher``, ``Cryptographer``, ...).
    """

    def __init__(self, log_name_prefix, actor=None):
        self.actor = actor
        self.f_logger = logging.getLogger("{}_file_log".format(log_name_prefix))
        self.c_logger = logging.getLogger("{}_console_log".format(log_name_prefix))

    def _add_prefix(self, msg):
        return msg if self.actor is None else "[{}]: {}".format(self.actor, msg)

    def _create_console_message(self, msg, **kwargs):
        s_message = _StructuredMessage(self._add_prefix(msg), **kwargs).to_dict()
        message = "{} {}".format(s_message["time"], s_message["message"])

        # s_message will always have at least two items (message and time).
        if len(s_message) > 2:
            params = "".join("{}={}, ".format(k, v) for k, v in s_message.items() if k not in ["message", "time"])

            # Remove the extra 2 characters (space and comma) and add all data to the final message.
            message += " ({})".format(params[:-2])

        return message

    @staticmethod
    def _create_file_message(msg, **kwargs):
        return json.dumps(_StructuredMessage(msg, **kwargs).to_dict())

    def info(self, msg, **kwargs):
        """
        Logs an ``INFO`` level message to stdout and file.

        Args:
             msg (:obj:`str`): the message to be logged.
             kwargs: a ``key:value`` collection parameters to be added to the output.
        """

        self.f_logger.info(self._create_file_message(msg, **kwargs))
        self.c_logger.info(self._create_console_message(msg, **kwargs))

    def debug(self, msg, **kwargs):
        """
        Logs a ``DEBUG`` level message to stdout and file.

        Args:
             msg (:obj:`str`): the message to be logged.
             kwargs: a ``key:value`` collection parameters to be added to the output.
        """

        self.f_logger.debug(self._create_file_message(msg, **kwargs))
        self.c_logger.debug(self._create_console_message(msg, **kwargs))

    def error(self, msg, **kwargs):
        """
        Logs an ``ERROR`` level message to stdout and file.

        Args:
             msg (:obj:`str`): the message to be logged.
             kwargs: a ``key:value`` collection parameters to be added to the output.
        """

        self.f_logger.error(self._create_file_message(msg, **kwargs))
        self.c_logger.error(self._create_console_message(msg, **kwargs))

    def warning(self, msg, **kwargs):
        """
        Logs a ``WARNING`` level message to stdout and file.

        Args:
             msg (:obj:`str`): the message to be logged.
             kwargs: a ``key:value`` collection parameters to be added to the output.
        """

        self.f_logger.warning(self._create_file_message(msg, **kwargs))
        self.c_logger.warning(self._create_console_message(msg, **kwargs))
