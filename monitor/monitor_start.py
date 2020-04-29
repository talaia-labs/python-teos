from monitor.searcher import Searcher

from common.logger import Logger

LOG_PREFIX = "Main"
logger = Logger(actor="System Monitor Main", log_name_prefix=LOG_PREFIX)

def main():
    logger.info("Setting up the system monitor.")

    # Create and start searcher.
    searcher = Searcher(None, None, CLOUD_ID, AUTH_USER, AUTH_PW)
    searcher.start()

if __name__ == "__main__":
    main()

