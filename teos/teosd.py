import os
from sys import argv, exit
from getopt import getopt, GetoptError
from signal import signal, SIGINT, SIGQUIT, SIGTERM

from common.logger import Logger
from common.config_loader import ConfigLoader
from common.cryptographer import Cryptographer
from common.tools import setup_logging, setup_data_folder

from teos.api import API
from teos.help import show_usage
from teos.watcher import Watcher
from teos.builder import Builder
from teos.carrier import Carrier
from teos.users_dbm import UsersDBM
from teos.inspector import Inspector
from teos.responder import Responder
from teos.gatekeeper import Gatekeeper
from teos.chain_monitor import ChainMonitor
from teos.block_processor import BlockProcessor
from teos.appointments_dbm import AppointmentsDBM
from teos.tools import can_connect_to_bitcoind, in_correct_network
from teos import LOG_PREFIX, DATA_DIR, DEFAULT_CONF, CONF_FILE_NAME

logger = Logger(actor="Daemon", log_name_prefix=LOG_PREFIX)


def handle_signals(signal_received, frame):
    logger.info("Closing connection with appointments db")
    db_manager.db.close()
    chain_monitor.terminate = True

    logger.info("Shutting down TEOS")
    exit(0)


def main(command_line_conf):
    global db_manager, chain_monitor

    signal(SIGINT, handle_signals)
    signal(SIGTERM, handle_signals)
    signal(SIGQUIT, handle_signals)

    # Loads config and sets up the data folder and log file
    data_dir = command_line_conf.get("DATA_DIR") if "DATA_DIR" in command_line_conf else DATA_DIR
    config_loader = ConfigLoader(data_dir, CONF_FILE_NAME, DEFAULT_CONF, command_line_conf)
    config = config_loader.build_config()
    setup_data_folder(data_dir)
    setup_logging(config.get("LOG_FILE"), LOG_PREFIX)

    logger.info("Starting TEOS")
    db_manager = AppointmentsDBM(config.get("APPOINTMENTS_DB_PATH"))

    bitcoind_connect_params = {k: v for k, v in config.items() if k.startswith("BTC")}
    bitcoind_feed_params = {k: v for k, v in config.items() if k.startswith("FEED")}

    if not can_connect_to_bitcoind(bitcoind_connect_params):
        logger.error("Can't connect to bitcoind. Shutting down")

    elif not in_correct_network(bitcoind_connect_params, config.get("BTC_NETWORK")):
        logger.error("bitcoind is running on a different network, check conf.py and bitcoin.conf. Shutting down")

    else:
        try:
            secret_key_der = Cryptographer.load_key_file(config.get("TEOS_SECRET_KEY"))
            if not secret_key_der:
                raise IOError("TEOS private key can't be loaded")

            block_processor = BlockProcessor(bitcoind_connect_params)
            carrier = Carrier(bitcoind_connect_params)

            responder = Responder(db_manager, carrier, block_processor)
            watcher = Watcher(
                db_manager,
                block_processor,
                responder,
                secret_key_der,
                config.get("MAX_APPOINTMENTS"),
                config.get("EXPIRY_DELTA"),
            )

            # Create the chain monitor and start monitoring the chain
            chain_monitor = ChainMonitor(
                watcher.block_queue, watcher.responder.block_queue, block_processor, bitcoind_feed_params
            )

            watcher_appointments_data = db_manager.load_watcher_appointments()
            responder_trackers_data = db_manager.load_responder_trackers()

            if len(watcher_appointments_data) == 0 and len(responder_trackers_data) == 0:
                logger.info("Fresh bootstrap")

                watcher.awake()
                watcher.responder.awake()

            else:
                logger.info("Bootstrapping from backed up data")

                # Update the Watcher backed up data if found.
                if len(watcher_appointments_data) != 0:
                    watcher.appointments, watcher.locator_uuid_map = Builder.build_appointments(
                        watcher_appointments_data
                    )

                # Update the Responder with backed up data if found.
                if len(responder_trackers_data) != 0:
                    watcher.responder.trackers, watcher.responder.tx_tracker_map = Builder.build_trackers(
                        responder_trackers_data
                    )

                # Awaking components so the states can be updated.
                watcher.awake()
                watcher.responder.awake()

                last_block_watcher = db_manager.load_last_block_hash_watcher()
                last_block_responder = db_manager.load_last_block_hash_responder()

                # Populate the block queues with data if they've missed some while offline. If the blocks of both match
                # we don't perform the search twice.

                # FIXME: 32-reorgs-offline dropped txs are not used at this point.
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

                # If only one of the instances needs to be updated, it can be done separately.
                if len(missed_blocks_watcher) == 0 and len(missed_blocks_responder) != 0:
                    Builder.populate_block_queue(watcher.responder.block_queue, missed_blocks_responder)
                    watcher.responder.block_queue.join()

                elif len(missed_blocks_responder) == 0 and len(missed_blocks_watcher) != 0:
                    Builder.populate_block_queue(watcher.block_queue, missed_blocks_watcher)
                    watcher.block_queue.join()

                # Otherwise they need to be updated at the same time, block by block
                elif len(missed_blocks_responder) != 0 and len(missed_blocks_watcher) != 0:
                    Builder.update_states(watcher, missed_blocks_watcher, missed_blocks_responder)

            # Fire the API and the ChainMonitor
            # FIXME: 92-block-data-during-bootstrap-db
            chain_monitor.monitor_chain()
            gatekeeper = Gatekeeper(UsersDBM(config.get("USERS_DB_PATH")), config.get("DEFAULT_SLOTS"))
            inspector = Inspector(block_processor, config.get("MIN_TO_SELF_DELAY"))
            API(config.get("API_BIND"), config.get("API_PORT"), inspector, watcher, gatekeeper).start()
        except Exception as e:
            logger.error("An error occurred: {}. Shutting down".format(e))
            exit(1)


if __name__ == "__main__":
    command_line_conf = {}

    try:
        opts, _ = getopt(
            argv[1:],
            "h",
            [
                "apiconnect=",
                "apiport=",
                "btcnetwork=",
                "btcrpcuser=",
                "btcrpcpassword=",
                "btcrpcconnect=",
                "btcrpcport=",
                "datadir=",
                "help",
            ],
        )
        for opt, arg in opts:
            if opt in ["--apibind"]:
                command_line_conf["API_BIND"] = arg
            if opt in ["--apiport"]:
                command_line_conf["API_PORT"] = arg
            if opt in ["--btcnetwork"]:
                command_line_conf["BTC_NETWORK"] = arg
            if opt in ["--btcrpcuser"]:
                command_line_conf["BTC_RPC_USER"] = arg
            if opt in ["--btcrpcpassword"]:
                command_line_conf["BTC_RPC_PASSWORD"] = arg
            if opt in ["--btcrpcconnect"]:
                command_line_conf["BTC_RPC_CONNECT"] = arg
            if opt in ["--btcrpcport"]:
                try:
                    command_line_conf["BTC_RPC_PORT"] = int(arg)
                except ValueError:
                    exit("btcrpcport must be an integer")
            if opt in ["--datadir"]:
                command_line_conf["DATA_DIR"] = os.path.expanduser(arg)
            if opt in ["-h", "--help"]:
                exit(show_usage())

    except GetoptError as e:
        exit(e)

    main(command_line_conf)
