import json
import logging
import logging.config
import structlog
from datetime import datetime

configured = False # set to True once setuo_logging is called

timestamper = structlog.processors.TimeStamper(fmt="%d/%m/%Y %H:%M:%S")
pre_chain = [
    # Add the log level and a timestamp to the event_dict if the log entry
    # is not from structlog.
    structlog.stdlib.add_log_level,
    timestamper,
]


def setup_logging(log_file_path, silent=False):
    """
    Configures the logging options. It must be called only once, before using get_logger.

    Args:
        log_file_path(:obj:`str`): the path and name of the log file.
        silent(:obj:`str`): if True, only critical errors will be shown to console.

    Raises:
        (:obj:`RuntimeError`) setup_logger had already been called.

    """

    global configured

    if configured:
        raise RuntimeError("logging was already configured.")

    logging.config.dictConfig({
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": structlog.dev.ConsoleRenderer(colors=False),
                    "foreign_pre_chain": pre_chain,
                },
            },
            "handlers": {
                "console": {
                    "level": "INFO" if not silent else "CRITICAL",
                    "class": "logging.StreamHandler",
                    "formatter": "plain",
                },
                "file": {
                    "level": "DEBUG",
                    "class": "logging.handlers.WatchedFileHandler",
                    "filename": log_file_path,
                    "formatter": "plain",
                },
            },
            "loggers": {
                "": {
                    "handlers": ["console", "file"],
                    "level": "DEBUG",
                    "propagate": True,
                },
            }
    })

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    configured = True


def get_logger(actor=None):
    """
    Returns a logger, that has the given `actor` in all future log entries.

    Args:
        actor(:obj:`str`): the name of the "actor" field that will be attached to all the logs issued by this logger.

    """
    return structlog.get_logger(actor=actor)

