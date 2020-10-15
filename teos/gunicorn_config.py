import os
import structlog
from logging.handlers import SocketHandler


logging_port = os.environ.get("LOG_SERVER_PORT")
timestamper = structlog.processors.TimeStamper(fmt="%d/%m/%Y %H:%M:%S")


class FormattedSocketHandler(SocketHandler):
    """ Works in the same way as SocketHandler, but it uses formatters. """

    def emit(self, record):
        """
        Works exactly like SocketHandler.emit but formats the record before sending it.
        record.args is set to none since they are already used by self.format, otherwise makePickle would try to
        use them again and fail.

        Args:
            record (:obj:LogRecord <logging.LogRecord>): the record to be emitted.
        """
        try:
            record.msg = self.format(record)
            record.args = None

            s = self.makePickle(record)
            self.send(s)

        except Exception:
            self.handleError(record)


def add_component(logger, name, event_dict):
    """ Adds the component name to the structlog."""
    event_dict["component"] = "API"
    return event_dict


# Add the timestamp and component to the entry if the entry is not from structlog.
pre_chain = [timestamper, add_component]


# Config dict that will be used by gunicorn
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["error_console"],
            "propagate": False,
            "qualname": "gunicorn.error",
        },
        "gunicorn.access": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
            "qualname": "gunicorn.access",
        },
    },
    "formatters": {
        "json_formatter": {
            "()": structlog.stdlib.ProcessorFormatter,
            "processor": structlog.processors.JSONRenderer(),
            "foreign_pre_chain": pre_chain,
        }
    },
    "handlers": {
        "error_console": {
            "level": "DEBUG",
            "class": "teos.gunicorn_config.FormattedSocketHandler",
            "host": "localhost",
            "port": logging_port,
            "formatter": "json_formatter",
        },
        "console": {
            "level": "DEBUG",
            "class": "teos.gunicorn_config.FormattedSocketHandler",
            "host": "localhost",
            "port": logging_port,
            "formatter": "json_formatter",
        },
    },
}
