import os
from sys import argv, exit
from getopt import getopt, GetoptError
from signal import signal, SIGINT, SIGQUIT, SIGTERM

from common.logger import setup_logging, get_logger
from common.config_loader import ConfigLoader
from common.cryptographer import Cryptographer
from common.tools import setup_data_folder

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
from teos import DATA_DIR, DEFAULT_CONF, CONF_FILE_NAME
from teos.tools import can_connect_to_bitcoind, in_correct_network, get_default_rpc_port

logger = get_logger(component="Daemon")


def handle_signals(signal_received, frame):
    logger.info("Closing connection with appointments db")
    db_manager.db.close()
    chain_monitor.terminate = True

    logger.info("Shutting down TEOS")
    exit(0)


def main(command_line_conf):
    global db_manager, chain_monitor

    try:
        signal(SIGINT, handle_signals)
        signal(SIGTERM, handle_signals)
        signal(SIGQUIT, handle_signals)

        # Loads config and sets up the base data folder and log file
        data_dir = command_line_conf.pop("DATA_DIR") if "DATA_DIR" in command_line_conf else DATA_DIR
        config_loader = ConfigLoader(data_dir, CONF_FILE_NAME, DEFAULT_CONF, command_line_conf)
        config = config_loader.build_config()

        network = config.get("BTC_NETWORK")

        # Set default RPC port if not overwritten by the user.
        if "BTC_RPC_PORT" not in config_loader.overwritten_fields:
            config["BTC_RPC_PORT"] = get_default_rpc_port(network)

        # if not on mainnet, data is in the appropriate subfolder
        data_dir_network = data_dir if network == "mainnet" else os.path.join(data_dir, network)

        setup_data_folder(data_dir_network)
        setup_logging(config.get("LOG_FILE"))

        logger.info("Starting TEOS")

        bitcoind_connect_params = {k: v for k, v in config.items() if k.startswith("BTC")}
        bitcoind_feed_params = {k: v for k, v in config.items() if k.startswith("BTC_FEED")}

        if not can_connect_to_bitcoind(bitcoind_connect_params):
            logger.error("Cannot connect to bitcoind. Shutting down")

        elif not in_correct_network(bitcoind_connect_params, network):
            logger.error("bitcoind is running on a different network, check conf.py and bitcoin.conf. Shutting down")

        else:
            if not os.path.exists(config.get("TEOS_SECRET_KEY")) or config.get("OVERWRITE_KEY"):
                logger.info("Generating a new key pair")
                sk = Cryptographer.generate_key()
                Cryptographer.save_key_file(sk.to_der(), "teos_sk", data_dir_network)

            else:
                logger.info("Tower identity found. Loading keys")
                secret_key_der = Cryptographer.load_key_file(config.get("TEOS_SECRET_KEY"))

                if not secret_key_der:
                    raise IOError("TEOS private key cannot be loaded")
                sk = Cryptographer.load_private_key_der(secret_key_der)

            logger.info("tower_id = {}".format(Cryptographer.get_compressed_pk(sk.public_key)))
            block_processor = BlockProcessor(bitcoind_connect_params)
            carrier = Carrier(bitcoind_connect_params)

            gatekeeper = Gatekeeper(
                UsersDBM(config.get("USERS_DB_PATH")),
                block_processor,
                config.get("SUBSCRIPTION_SLOTS"),
                config.get("SUBSCRIPTION_DURATION"),
                config.get("EXPIRY_DELTA"),
            )
            db_manager = AppointmentsDBM(config.get("APPOINTMENTS_DB_PATH"))
            responder = Responder(db_manager, gatekeeper, carrier, block_processor)
            watcher = Watcher(
                db_manager,
                gatekeeper,
                block_processor,
                responder,
                sk,
                config.get("MAX_APPOINTMENTS"),
                config.get("LOCATOR_CACHE_SIZE"),
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
            inspector = Inspector(block_processor, config.get("MIN_TO_SELF_DELAY"))
            API(config.get("API_BIND"), config.get("API_PORT"), inspector, watcher).start()
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
                "apibind=",
                "apiport=",
                "btcnetwork=",
                "btcrpcuser=",
                "btcrpcpassword=",
                "btcrpcconnect=",
                "btcrpcport=",
                "btcfeedconnect=",
                "btcfeedport=",
                "datadir=",
                "overwritekey",
                "help",
            ],
        )
        for opt, arg in opts:
            if opt in ["--apibind"]:
                command_line_conf["API_BIND"] = arg
            if opt in ["--apiport"]:
                try:
                    command_line_conf["API_PORT"] = int(arg)
                except ValueError:
                    exit("apiport must be an integer")
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
            if opt in ["--btcfeedconnect"]:
                command_line_conf["BTC_FEED_CONNECT"] = arg
            if opt in ["--btcfeedport"]:
                try:
                    command_line_conf["BTC_FEED_PORT"] = int(arg)
                except ValueError:
                    exit("btcfeedport must be an integer")
            if opt in ["--datadir"]:
                command_line_conf["DATA_DIR"] = os.path.expanduser(arg)
            if opt in ["--overwritekey"]:
                command_line_conf["OVERWRITE_KEY"] = True
            if opt in ["-h", "--help"]:
                exit(show_usage())

    except GetoptError as e:
        exit(e)

    main(command_line_conf)
