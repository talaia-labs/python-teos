import time
import json

from pisa import f_logger, c_logger


class _StructuredMessage:
    def __init__(self, message, **kwargs):
        self.message = message
        self.time = time.asctime()
        self.kwargs = kwargs

    def __str__(self):
        return {**self.kwargs, "message": self.message, "time": self.time}


class Logger:
    """
    The :class:`Logger` is the class in charge of logging events into the log file.

    Args:
        actor (:obj:`str`): the system actor that is logging the event (e.g. ``Watcher``, ``Cryptographer``, ...).
    """

    def __init__(self, actor=None):
        self.actor = actor

    def _add_prefix(self, msg):
        return msg if self.actor is None else "[{}] {}".format(self.actor, msg)

    def _create_console_message(self, msg, **kwargs):
        return _StructuredMessage(self._add_prefix(msg), actor=self.actor, **kwargs).message

    def _create_file_message(self, msg, **kwargs):
        return json.dumps(_StructuredMessage(msg, actor=self.actor, **kwargs).__str__())

    def info(self, msg, **kwargs):
        """
        Logs an ``INFO`` level message to stdout and file.

        Args:
             msg (:obj:`str`): the message to be logged.
             kwargs: a ``key:value`` collection parameters to be added to the output.
        """

        f_logger.info(self._create_file_message(msg, **kwargs))
        c_logger.info(self._create_console_message(msg, **kwargs))

    def debug(self, msg, **kwargs):
        """
        Logs an ``DEBUG`` level message to stdout and file.

        Args:
             msg (:obj:`str`): the message to be logged.
             kwargs: a ``key:value`` collection parameters to be added to the output.
        """

        f_logger.debug(self._create_file_message(msg, **kwargs))
        c_logger.debug(self._create_console_message(msg, **kwargs))

    def error(self, msg, **kwargs):
        """
        Logs an ``ERROR`` level message to stdout and file.

        Args:
             msg (:obj:`str`): the message to be logged.
             kwargs: a ``key:value`` collection parameters to be added to the output.
        """

        f_logger.error(self._create_file_message(msg, **kwargs))
        c_logger.error(self._create_console_message(msg, **kwargs))

    def warning(self, msg, **kwargs):
        """
        Logs an ``WARNING`` level message to stdout and file.

        Args:
             msg (:obj:`str`): the message to be logged.
             kwargs: a ``key:value`` collection parameters to be added to the output.
        """

        f_logger.warning(self._create_file_message(msg, **kwargs))
        c_logger.warning(self._create_console_message(msg, **kwargs))
