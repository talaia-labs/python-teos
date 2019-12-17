from getopt import getopt
from sys import argv, exit
from signal import signal, SIGINT, SIGQUIT, SIGTERM

from pisa.conf import DB_PATH
from common.logger import Logger
from pisa.api import start_api
from pisa.watcher import Watcher
from pisa.builder import Builder
from pisa.conf import BTC_NETWORK, PISA_SECRET_KEY
from pisa.responder import Responder
from pisa.db_manager import DBManager
from pisa.block_processor import BlockProcessor
from pisa.tools import can_connect_to_bitcoind, in_correct_network

logger = Logger("Daemon")


def handle_signals(signal_received, frame):
    logger.info("Closing connection with appointments db")
    db_manager.db.close()

    logger.info("Shutting down PISA")
    exit(0)


if __name__ == "__main__":
    logger.info("Starting PISA")

    signal(SIGINT, handle_signals)
    signal(SIGTERM, handle_signals)
    signal(SIGQUIT, handle_signals)

    opts, _ = getopt(argv[1:], "", [""])
    for opt, arg in opts:
        # FIXME: Leaving this here for future option/arguments
        pass

    if not can_connect_to_bitcoind():
        logger.error("Can't connect to bitcoind. Shutting down")

    elif not in_correct_network(BTC_NETWORK):
        logger.error("bitcoind is running on a different network, check conf.py and bitcoin.conf. Shutting down")

    else:
        try:
            db_manager = DBManager(DB_PATH)

            watcher_appointments_data = db_manager.load_watcher_appointments()
            responder_trackers_data = db_manager.load_responder_trackers()

            with open(PISA_SECRET_KEY, "rb") as key_file:
                secret_key_der = key_file.read()

            watcher = Watcher(db_manager, secret_key_der)

            if len(watcher_appointments_data) == 0 and len(responder_trackers_data) == 0:
                logger.info("Fresh bootstrap")

            else:
                logger.info("Bootstrapping from backed up data")
                block_processor = BlockProcessor()

                last_block_watcher = db_manager.load_last_block_hash_watcher()
                last_block_responder = db_manager.load_last_block_hash_responder()

                missed_blocks_watcher = block_processor.get_missed_blocks(last_block_watcher)
                missed_blocks_responder = (
                    missed_blocks_watcher
                    if last_block_watcher == last_block_responder
                    else block_processor.get_missed_blocks(last_block_responder)
                )

                responder = Responder(db_manager)
                responder.trackers, responder.tx_tracker_map = Builder.build_trackers(responder_trackers_data)
                responder.block_queue = Builder.build_block_queue(missed_blocks_responder)

                watcher.responder = responder
                watcher.appointments, watcher.locator_uuid_map = Builder.build_appointments(watcher_appointments_data)
                watcher.block_queue = Builder.build_block_queue(missed_blocks_watcher)

            # Create an instance of the Watcher and fire the API
            start_api(watcher)

        except Exception as e:
            logger.error("An error occurred: {}. Shutting down".format(e))
            exit(1)
