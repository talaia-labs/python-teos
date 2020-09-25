import logging.handlers

SHUTDOWN_GRACE_TIME = 10  # Grace time in seconds to complete any pending call when stopping one of the services of TEOS
TCP_LOGGING_PORT = logging.handlers.DEFAULT_TCP_LOGGING_PORT  # The port used for the tcp logging service is 9020
OUTDATED_USERS_CACHE_SIZE_BLOCKS = 10  # Size of the users cache, in blocks
