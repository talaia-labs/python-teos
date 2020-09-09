import json
import logging
import logging.config
import logging.handlers
import structlog

from common.constants import TCP_LOGGING_PORT

configured = False  # set to True once setup_logging is called


class JsonMsgLogger(logging.Logger):
    """
    Works exactly like logging.Logger but represents dict messages as json. Useful to prevent dicts being cast
    to strings via str().
    """

    def makeRecord(self, *args, **kwargs):
        rv = super().makeRecord(*args, **kwargs)
        if isinstance(rv.msg, dict):
            rv.msg = json.dumps(rv.msg)

        return rv


def setup_logging():
    """
    Configures the logging options. It must be called only once, before using get_logger.

    Raises:
        :obj:`RuntimeError` setup_logging had already been called.
    """

    global configured

    if configured:
        raise RuntimeError("Logging was already configured")

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {  # filter out logs that do not come from teos
                "onlyteos": {"()": logging.Filter, "name": "teos"}
            },
            "handlers": {
                "socket": {
                    "level": "DEBUG",
                    "class": "logging.handlers.SocketHandler",
                    "host": "localhost",
                    "port": TCP_LOGGING_PORT,
                    "filters": ["onlyteos"],
                },
            },
            "loggers": {"": {"handlers": ["socket"], "level": "DEBUG", "propagate": True}},
        }
    )

    structlog.configure(
        processors=[
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="%d/%m/%Y %H:%M:%S"),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.setLoggerClass(JsonMsgLogger)
    configured = True


def get_logger(component=None):
    """
    Returns a logger, that has the given `component` in all future log entries.

    Returns:
        a proxy obtained from structlog.get_logger with the `component` as bound variable.

    Args:
        component(:obj:`str`): the value of the "component" field that will be attached to all the logs issued by this
            logger.
    """
    return structlog.get_logger("teos", component=component)
