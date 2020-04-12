from monitor.searcher import Searcher

from common.logger import Logger

logger = Logger(actor="System Monitor Main", log_name_prefix=LOG_PREFIX)

def main():
    logger.info("Setting up the system monitor.")

    # Create and start searcher.
    searcher = Searcher()
    searcher.start()

if __name__ == "__main__":
    main()

