import logging.handlers


# the grace time in seconds to complete any pending call when stopping one of the services of TEOS
SHUTDOWN_GRACE_TIME = 10

# The port used for the tcp logging service is 9020
TCP_LOGGING_PORT = logging.handlers.DEFAULT_TCP_LOGGING_PORT
