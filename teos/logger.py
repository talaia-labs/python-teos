import logging
import logging.config
import logging.handlers
import structlog
import pickle
import socketserver
from signal import signal, SIGINT
import struct
import select
import json
from io import StringIO

from teos.tools import ignore_signal

configured = False  # set to True once setup_logging is called


class JsonMsgLogger(logging.Logger):
    """
    Works exactly like ``logging.Logger`` but represents dict messages as json. Useful to prevent dicts being cast
    to strings via ``str()``.
    """

    def makeRecord(self, *args, **kwargs):
        """Makes a record where the message is json encoded."""
        rv = super().makeRecord(*args, **kwargs)
        if isinstance(rv.msg, dict):
            rv.msg = json.dumps(rv.msg)

        return rv


def setup_logging(logging_port):
    """
    Configures the logging options. It must be called only once, before using get_logger.

    Args:
        logging_port (:obj:`int`): the port where the logging server can be reached (localhost:logging_port)

    Raises:
        :obj:`RuntimeError`: if ``setup_logging`` had already been called.
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
                    "port": logging_port,
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
    Returns a :obj:`Logger`, that has the given `component` in all future log entries.

    Returns:
        A proxy obtained from ``structlog.get_logger`` with the ``component`` as bound variable.

    Args:
        component(:obj:`str`): the value of the ``component`` field that will be attached to all the logs issued by this
            logger.
    """
    return structlog.get_logger("teos", component=component)


def _repr(val):
    """Returns the representation of *val* if it's not a ``str``."""

    return val if isinstance(val, str) else repr(val)


def encode_event_dict(event_dict):
    """
    Encodes an event dictionary in a nicely formatted string, following the general format:

        ``timestamp [component] event (attr1=value1, attr2=value2, ...)``

    Where values that are not present are omitted. See unit tests for a more precise specification.
    """

    sio = StringIO()

    ts = event_dict.pop("timestamp", None)
    if ts:
        sio.write(str(ts) + " ")

    component = event_dict.pop("component", None)
    if component:
        sio.write("[" + component + "] ")

    log_level = event_dict.pop("log_level", None)
    if log_level and log_level != "INFO":
        sio.write(log_level + ": ")

    event = _repr(event_dict.pop("event"))

    sio.write(event)

    # Represent all the key=value elements still in event_dict
    key_value_part = ", ".join(key + "=" + _repr(event_dict[key]) for key in sorted(event_dict.keys()))
    if len(key_value_part) > 0:
        sio.write("  (" + key_value_part + ")")

    return sio.getvalue()


class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    """
    Handler for a streaming logging request. Sends to the logger any received log message, after some preprocessing.
    """

    # Taken almost verbatim from Python's logging cookbook.
    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length, followed by the :obj:`LogRecord` in pickle
        format. Logs the record according to whatever policy is configured locally.
        """

        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = struct.unpack(">L", chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            obj = pickle.loads(chunk)
            record = logging.makeLogRecord(obj)
            self.handle_log_record(record)

    @staticmethod
    def handle_log_record(record):
        """
        Processes log records received via the socket. The record's ``msg`` field is expected to be an encoded
        :obj:`dict` produced by :obj:`StructLog`. The :obj:`dict` is encoded to a string using ``encode_event_dict`` and
        sent to the logger with the name specified in the record.

        Args:
            record (:obj:`logging.LogRecord`): a log record.
        """

        event_dict = json.loads(record.msg)
        event_dict.update({"log_level": record.levelname})
        message = encode_event_dict(event_dict)

        logger = logging.getLogger(record.name)
        logger.log(record.levelno, message, exc_info=record.exc_info, stack_info=record.stack_info)


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    """
    Simple TCP socket-based logging receiver.

    Args:
        host (:obj:`str`): the hostname or ip where the logging server can be reached. Defaults to localhost.
        port (:obj:`int`): the port where the logging server can be reached. Defaults to 0 so the OS can pick a free
            one.
        handler (:obj:`StreamRequestHandler`): the log handler.
    """

    allow_reuse_address = True

    def __init__(self, host="localhost", port=0, handler=LogRecordStreamHandler):
        socketserver.ThreadingTCPServer.__init__(self, (host, port), handler)
        self.timeout = 1

    def serve_forever(self, poll_interval=0.5):
        """Serves the logger server until the tower is stopped."""

        while True:
            rd, wr, ex = select.select([self.socket.fileno()], [], [], self.timeout)
            if rd:
                self.handle_request()


def serve(log_file_path, logging_port, silent, ready):
    """
    Sets up logging on console and file, and serves the tcp logging server on ``localhost:tcp_logging_port``.
    This method is meant to be run in a separate process and provides the logging service.

    Args:
        log_file_path (:obj:`str`): the full path and log file name.
        logging_port (:obj:`int`): the port where the logging server can be reached (localhost:logging_port)
        silent (:obj:`bool`): if True, only ``CRITICAL`` errors are shown to console; otherwise ``INFO`` and above.
        ready (:obj:`multiprocessing.Event`): an event that is set once the logging server is ready.
    """

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "console": {"level": "INFO" if not silent else "CRITICAL", "class": "logging.StreamHandler"},
                "file": {"level": "DEBUG", "class": "logging.handlers.WatchedFileHandler", "filename": log_file_path},
            },
            "loggers": {"": {"handlers": ["console", "file"], "level": "DEBUG", "propagate": True}},
        }
    )

    # Ignore SIGINT so this process does not crash on CTRL+C, but comply on other signals
    signal(SIGINT, ignore_signal)

    tcpserver = LogRecordSocketReceiver(port=logging_port.value)
    logging_port.value = tcpserver.server_address[1]
    ready.set()
    tcpserver.serve_forever()
