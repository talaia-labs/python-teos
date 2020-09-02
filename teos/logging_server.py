import pickle
import logging
import logging.config
import logging.handlers
import socketserver
from signal import signal, SIGINT
import struct
import json

from common.constants import TCP_LOGGING_PORT

from io import StringIO


def _repr(val):
    """Returns the representation of *val* if it's not a ``str``."""

    return val if isinstance(val, str) else repr(val)


def encode_event_dict(event_dict):
    # TODO: docs
    sio = StringIO()

    ts = event_dict.pop("timestamp", None)
    if ts:
        sio.write(str(ts) + " ")

    component = event_dict.pop("component", None)
    if component:
        sio.write("[" + component + "] ")

    event = _repr(event_dict.pop("event"))

    sio.write(event)

    # Represent all the key=value elements still in event_dict
    key_value_part = ", ".join(key + "=" + _repr(event_dict[key]) for key in sorted(event_dict.keys()))
    if len(key_value_part) > 0:
        sio.write("  (" + key_value_part + ")")

    return sio.getvalue()


class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    """Handler for a streaming logging request.

    This basically logs the record using whatever logging policy is
    configured locally.
    """

    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length,
        followed by the LogRecord in pickle format. Logs the record
        according to whatever policy is configured locally.
        """

        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = struct.unpack(">L", chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            obj = self.unPickle(chunk)
            record = logging.makeLogRecord(obj)
            self.handle_log_record(record)

    def unPickle(self, data):
        return pickle.loads(data)

    def handle_log_record(self, record):
        """
        Processes log records received via the socket. The record's ``msg`` field is expected to be an encoded ``dict``
        produced by structlog. The ``dict`` is encoded to a string using ``encode_event_dict`` and sent to the logger
        with the name specified in the record.
        """

        event_dict = json.loads(record.msg.replace("'", '"'))
        message = encode_event_dict(event_dict)

        logger = logging.getLogger(record.name)
        logger.log(record.levelno, message)


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    """
    Simple TCP socket-based logging receiver suitable for testing.
    """

    allow_reuse_address = True

    def __init__(self, host="localhost", port=TCP_LOGGING_PORT, handler=LogRecordStreamHandler):
        socketserver.ThreadingTCPServer.__init__(self, (host, port), handler)
        self.abort = 0
        self.timeout = 1
        self.logname = None

    def serve_until_stopped(self):
        import select

        abort = 0
        while not abort:
            rd, wr, ex = select.select([self.socket.fileno()], [], [], self.timeout)
            if rd:
                self.handle_request()
            abort = self.abort


def serve(log_file_path):
    silent = False  # TODO, need to pass this

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {
                "console": {"level": "INFO" if not silent else "CRITICAL", "class": "logging.StreamHandler",},
                "file": {"level": "DEBUG", "class": "logging.handlers.WatchedFileHandler", "filename": log_file_path,},
            },
            "loggers": {"": {"handlers": ["console", "file"], "level": "DEBUG", "propagate": True}},
        }
    )

    tcpserver = LogRecordSocketReceiver()

    # Ignore SIGINT so this process does not crash on CTRL+C, but comply on other signals
    def ignore_signal(_, __):
        pass

    signal(SIGINT, ignore_signal)

    tcpserver.serve_until_stopped()
