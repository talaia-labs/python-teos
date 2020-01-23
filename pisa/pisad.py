import os
from getopt import getopt
from sys import argv, exit
from signal import signal, SIGINT, SIGQUIT, SIGTERM

from common.logger import Logger
from common.tools import check_conf_fields, setup_data_folder

from pisa.api import API
from pisa.watcher import Watcher
from pisa.builder import Builder
import pisa.conf as conf
from pisa.db_manager import DBManager
from pisa.chain_monitor import ChainMonitor
from pisa.block_processor import BlockProcessor
from pisa.tools import can_connect_to_bitcoind, in_correct_network

logger = Logger("Daemon")


def handle_signals(signal_received, frame):
    logger.info("Closing connection with appointments db")
    db_manager.db.close()
    chain_monitor.terminate = True

    logger.info("Shutting down PISA")
    exit(0)


def load_config(config):
    """
    Looks through all of the config options to make sure they contain the right type of data and builds a config
    dictionary. 

    Args:
        config (:obj:`module`): It takes in a config module object.

    Returns:
        :obj:`dict` A dictionary containing the config values.
    """

    conf_dict = {}

    data_folder = config.DATA_FOLDER
    if isinstance(data_folder, str):
        data_folder = os.path.expanduser(data_folder)
    else:
        raise ValueError("The provided user folder is invalid.")

    conf_fields = {
        "BTC_RPC_USER": {"value": config.BTC_RPC_USER, "type": str},
        "BTC_RPC_PASSWD": {"value": config.BTC_RPC_PASSWD, "type": str},
        "BTC_RPC_HOST": {"value": config.BTC_RPC_HOST, "type": str},
        "BTC_RPC_PORT": {"value": config.BTC_RPC_PORT, "type": int},
        "BTC_NETWORK": {"value": config.BTC_NETWORK, "type": str},
        "FEED_PROTOCOL": {"value": config.FEED_PROTOCOL, "type": str},
        "FEED_ADDR": {"value": config.FEED_ADDR, "type": str},
        "FEED_PORT": {"value": config.FEED_PORT, "type": int},
        "DATA_FOLDER": {"value": data_folder, "type": str},
        "MAX_APPOINTMENTS": {"value": config.MAX_APPOINTMENTS, "type": int},
        "EXPIRY_DELTA": {"value": config.EXPIRY_DELTA, "type": int},
        "MIN_TO_SELF_DELAY": {"value": config.MIN_TO_SELF_DELAY, "type": int},
        "SERVER_LOG_FILE": {"value": data_folder, "type": str},
        "PISA_SECRET_KEY": {"value": data_folder + config.PISA_SECRET_KEY, "type": str},
        "DB_PATH": {"value": data_folder + config.DB_PATH, "type": str},
    }

    check_conf_fields(conf_fields, logger)

    return conf_dict


def main():
    global db_manager, chain_monitor

    signal(SIGINT, handle_signals)
    signal(SIGTERM, handle_signals)
    signal(SIGQUIT, handle_signals)

    pisa_config = load_config(conf)
    logger.info("Starting PISA")

    setup_data_folder(pisa_config.get("DATA_FOLDER"), logger)
    db_manager = DBManager(pisa_config.get("DB_PATH"))

    if not can_connect_to_bitcoind():
        logger.error("Can't connect to bitcoind. Shutting down")

    elif not in_correct_network(pisa_config.get("BTC_NETWORK")):
        logger.error("bitcoind is running on a different network, check conf.py and bitcoin.conf. Shutting down")

    else:
        try:
            # Create the chain monitor and start monitoring the chain
            chain_monitor = ChainMonitor()
            chain_monitor.monitor_chain()

            watcher_appointments_data = db_manager.load_watcher_appointments()
            responder_trackers_data = db_manager.load_responder_trackers()

            with open(pisa_config.get("PISA_SECRET_KEY"), "rb") as key_file:
                secret_key_der = key_file.read()

            watcher = Watcher(db_manager, chain_monitor, secret_key_der, pisa_config)
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
                last_common_ancestor_responder = None
                missed_blocks_responder = None

                # Build Responder with backed up data if found
                if last_block_responder is not None:
                    last_common_ancestor_responder, dropped_txs_responder = block_processor.find_last_common_ancestor(
                        last_block_responder
                    )
                    missed_blocks_responder = block_processor.get_missed_blocks(last_common_ancestor_responder)

                    watcher.responder.trackers, watcher.responder.tx_tracker_map = Builder.build_trackers(
                        responder_trackers_data
                    )
                    watcher.responder.block_queue = Builder.build_block_queue(missed_blocks_responder)

                # Build Watcher. If the blocks of both match we don't perform the search twice.
                if last_block_watcher is not None:
                    if last_block_watcher == last_block_responder:
                        missed_blocks_watcher = missed_blocks_responder
                    else:
                        last_common_ancestor_watcher, dropped_txs_watcher = block_processor.find_last_common_ancestor(
                            last_block_watcher
                        )
                        missed_blocks_watcher = block_processor.get_missed_blocks(last_common_ancestor_watcher)

                    watcher.appointments, watcher.locator_uuid_map = Builder.build_appointments(
                        watcher_appointments_data
                    )
                    watcher.block_queue = Builder.build_block_queue(missed_blocks_watcher)

            # Fire the API
            API(watcher, config=pisa_config).start()

        except Exception as e:
            logger.error("An error occurred: {}. Shutting down".format(e))
            exit(1)


if __name__ == "__main__":
    opts, _ = getopt(argv[1:], "", [""])
    for opt, arg in opts:
        # FIXME: Leaving this here for future option/arguments
        pass

    main()
