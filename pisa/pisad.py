from getopt import getopt
from sys import argv, exit
from signal import signal, SIGINT, SIGQUIT, SIGTERM

from common.logger import Logger

from pisa import config, LOG_PREFIX
from pisa.api import API
from pisa.watcher import Watcher
from pisa.builder import Builder
from pisa.db_manager import DBManager
from pisa.chain_monitor import ChainMonitor
from pisa.block_processor import BlockProcessor
from pisa.tools import can_connect_to_bitcoind, in_correct_network

logger = Logger(actor="Daemon", log_name_prefix=LOG_PREFIX)


def handle_signals(signal_received, frame):
    logger.info("Closing connection with appointments db")
    db_manager.db.close()
    chain_monitor.terminate = True

    logger.info("Shutting down PISA")
    exit(0)


def main():
    global db_manager, chain_monitor

    signal(SIGINT, handle_signals)
    signal(SIGTERM, handle_signals)
    signal(SIGQUIT, handle_signals)

    logger.info("Starting PISA")
    db_manager = DBManager(config.get("DB_PATH"))

    if not can_connect_to_bitcoind():
        logger.error("Can't connect to bitcoind. Shutting down")

    elif not in_correct_network(config.get("BTC_NETWORK")):
        logger.error("bitcoind is running on a different network, check conf.py and bitcoin.conf. Shutting down")

    else:
        try:
            # Create the chain monitor and start monitoring the chain
            chain_monitor = ChainMonitor()
            chain_monitor.monitor_chain()

            watcher_appointments_data = db_manager.load_watcher_appointments()
            responder_trackers_data = db_manager.load_responder_trackers()

            with open(config.get("PISA_SECRET_KEY"), "rb") as key_file:
                secret_key_der = key_file.read()

            watcher = Watcher(db_manager, chain_monitor, secret_key_der, config)
            chain_monitor.attach_watcher(watcher.block_queue, watcher.asleep)
            chain_monitor.attach_responder(watcher.responder.block_queue, watcher.responder.asleep)

            if len(watcher_appointments_data) == 0 and len(responder_trackers_data) == 0:
                logger.info("Fresh bootstrap")

            else:
                logger.info("Bootstrapping from backed up data")
                block_processor = BlockProcessor()

                last_block_watcher = db_manager.load_last_block_hash_watcher()
                last_block_responder = db_manager.load_last_block_hash_responder()

                # FIXME: 32-reorgs-offline dropped txs are not used at this point.
                # Get the blocks missed by both the Watcher and the Responder. If the blocks of both match we don't
                # perform the search twice.
                last_common_ancestor_watcher, dropped_txs_watcher = block_processor.find_last_common_ancestor(
                    last_block_watcher
                )
                missed_blocks_watcher = block_processor.get_missed_blocks(last_common_ancestor_watcher)

                if last_block_watcher == last_block_responder:
                    dropped_txs_responder = dropped_txs_watcher
                    missed_blocks_responder = missed_blocks_watcher

                else:
                    last_common_ancestor_responder, dropped_txs_responder = block_processor.find_last_common_ancestor(
                        last_block_responder
                    )
                    missed_blocks_responder = block_processor.get_missed_blocks(last_common_ancestor_responder)

                # Build and update the Watcher.
                if len(watcher_appointments_data) != 0:
                    watcher.appointments, watcher.locator_uuid_map = Builder.build_appointments(
                        watcher_appointments_data
                    )

                # Build Responder with backed up data if found
                if len(responder_trackers_data) != 0:
                    watcher.responder.trackers, watcher.responder.tx_tracker_map = Builder.build_trackers(
                        responder_trackers_data
                    )

                # If only one of the instances needs to be updated, it can be done separately.
                if len(missed_blocks_watcher) == 0 and len(missed_blocks_responder) != 0:
                    Builder.populate_block_queue(watcher.responder.block_queue, missed_blocks_responder)
                    watcher.responder.awake()
                    watcher.responder.block_queue.join()

                elif len(missed_blocks_responder) == 0 and len(missed_blocks_watcher) != 0:
                    Builder.populate_block_queue(watcher.block_queue, missed_blocks_watcher)
                    watcher.awake()
                    watcher.block_queue.join()

                # Otherwise the need to be updated at the same time, block by block
                elif len(missed_blocks_responder) != 0 and len(missed_blocks_watcher) != 0:
                    Builder.update_states(watcher, missed_blocks_watcher, missed_blocks_responder)

                # Awake the Watcher/Responder if they ended up with pending work
                if watcher.appointments and watcher.asleep:
                    watcher.awake()
                if watcher.responder.trackers and watcher.responder.asleep:
                    watcher.responder.awake()

            # Fire the API
            API(watcher, config=config).start()
        except Exception as e:
            logger.error("An error occurred: {}. Shutting down".format(e))
            exit(1)


if __name__ == "__main__":
    opts, _ = getopt(argv[1:], "", [""])
    for opt, arg in opts:
        # FIXME: Leaving this here for future option/arguments
        pass

    main()
