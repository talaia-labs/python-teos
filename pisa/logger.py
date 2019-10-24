import time
import json

from pisa import f_logger, c_logger


class StructuredMessage(object):
    def __init__(self, message, **kwargs):
        self.message = message
        self.time = time.asctime()
        self.kwargs = kwargs

    def __str__(self):
        return {**self.kwargs, "message": self.message, "time": self.time}


class Logger(object):
    def __init__(self, actor=None):
        self.actor = actor

    def _add_prefix(self, msg):
        return msg if self.actor is None else "[{}] {}".format(self.actor, msg)

    def create_console_message(self, msg, **kwargs):
        return StructuredMessage(self._add_prefix(msg), actor=self.actor, **kwargs).message

    def create_file_message(self, msg, **kwargs):
        return json.dumps(StructuredMessage(msg, actor=self.actor, **kwargs).__str__())

    def info(self, msg, **kwargs):
        f_logger.info(self.create_file_message(msg, **kwargs))
        c_logger.info(self.create_console_message(msg, **kwargs))

    def debug(self, msg, **kwargs):
        f_logger.debug(self.create_file_message(msg, **kwargs))
        c_logger.debug(self.create_console_message(msg, **kwargs))

    def error(self, msg, **kwargs):
        f_logger.error(self.create_file_message(msg, **kwargs))
        c_logger.error(self.create_console_message(msg, **kwargs))

    def warning(self, msg, **kwargs):
        f_logger.warning(self.create_file_message(msg, **kwargs))
        c_logger.warning(self.create_console_message(msg, **kwargs))
