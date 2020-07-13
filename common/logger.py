import logging
import logging.config
from io import StringIO
import structlog

configured = False  # set to True once setup_logging is called

timestamper = structlog.processors.TimeStamper(fmt="%d/%m/%Y %H:%M:%S")
pre_chain = [timestamper]


# Stripped down version of structlog.dev.ConsoleRenderer, adding the "component" instead of the level.
class CustomLogRenderer:
    """
    Render ``event_dict``. It renders the timestamp, followed by the component within "[]" (unless it's None),
    followed by the event, then any remaining item in ``event_dict`` in the key=value format.
    """

    def _repr(self, val):
        """Returns the representation of *val* if it's not a ``str``."""
        return val if isinstance(val, str) else repr(val)

    def __call__(self, _, __, event_dict):
        """Returns ``event_dict`` rendered as a string."""
        sio = StringIO()

        ts = event_dict.pop("timestamp", None)
        if ts:
            sio.write(str(ts) + " ")

        component = event_dict.pop("component", None)
        if component:
            sio.write("[" + component + "] ")

        event = self._repr(event_dict.pop("event"))

        sio.write(event)

        # Represent all the key=value elements still in event_dict
        key_value_part = ", ".join(key + "=" + self._repr(event_dict[key]) for key in sorted(event_dict.keys()))
        if len(key_value_part) > 0:
            sio.write("  (" + key_value_part + ")")

        return sio.getvalue()


def setup_logging(log_file_path, silent=False):
    """
    Configures the logging options. It must be called only once, before using get_logger.

    Args:
        log_file_path (:obj:`str`): the path and name of the log file.
        silent (:obj:`str`): if True, only critical errors will be shown to console.

    Raises:
        :obj:`RuntimeError` setup_logger had already been called.
    """

    global configured

    if configured:
        raise RuntimeError("Logging was already configured")

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processor": CustomLogRenderer(),
                    "foreign_pre_chain": pre_chain,
                }
            },
            "filters": {  # filter out logs that do not come from teos
                "onlyteos": {"()": logging.Filter, "name": "teos"}
            },
            "handlers": {
                "console": {
                    "level": "INFO" if not silent else "CRITICAL",
                    "class": "logging.StreamHandler",
                    "formatter": "plain",
                    "filters": ["onlyteos"],
                },
                "file": {
                    "level": "DEBUG",
                    "class": "logging.handlers.WatchedFileHandler",
                    "filename": log_file_path,
                    "formatter": "plain",
                    "filters": ["onlyteos"],
                },
            },
            "loggers": {"": {"handlers": ["console", "file"], "level": "DEBUG", "propagate": True}},
        }
    )

    structlog.configure(
        processors=[
            structlog.stdlib.PositionalArgumentsFormatter(),
            timestamper,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

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
