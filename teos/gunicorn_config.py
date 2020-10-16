import os
import structlog
from teos.logger import add_api_component, timestamper


logging_port = os.environ.get("LOG_SERVER_PORT")


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
            "foreign_pre_chain": [timestamper, add_api_component],
        }
    },
    "handlers": {
        "error_console": {
            "level": "DEBUG",
            "class": "teos.logger.FormattedSocketHandler",
            "host": "localhost",
            "port": logging_port,
            "formatter": "json_formatter",
        },
        "console": {
            "level": "DEBUG",
            "class": "teos.logger.FormattedSocketHandler",
            "host": "localhost",
            "port": logging_port,
            "formatter": "json_formatter",
        },
    },
}
