import os
import daemon
import subprocess
from sys import argv, exit
from multiprocessing import Process
from getopt import getopt, GetoptError
from signal import signal, SIGINT, SIGQUIT, SIGTERM

from common.logger import setup_logging, get_logger
from common.config_loader import ConfigLoader
from common.cryptographer import Cryptographer
from common.tools import setup_data_folder

import teos.rpc as rpc
from teos.help import show_usage
from teos.watcher import Watcher
from teos.builder import Builder
from teos.carrier import Carrier
from teos.users_dbm import UsersDBM
from teos.responder import Responder
from teos.gatekeeper import Gatekeeper
from teos.internal_api import InternalAPI
from teos.chain_monitor import ChainMonitor
from teos.block_processor import BlockProcessor
from teos.appointments_dbm import AppointmentsDBM
from teos import DATA_DIR, DEFAULT_CONF, CONF_FILE_NAME
from teos.tools import can_connect_to_bitcoind, in_correct_network, get_default_rpc_port

logger = get_logger(component="Daemon")
parent_pid = os.getpid()

INTERNAL_API_HOST = "localhost"
INTERNAL_API_PORT = "50051"
INTERNAL_API_ENDPOINT = f"{INTERNAL_API_HOST}:{INTERNAL_API_PORT}"


def handle_signals(signal_received, frame):
    if os.getpid() == parent_pid:
        logger.info("Closing connection with appointments db")
        db_manager.db.close()
        chain_monitor.terminate = True

        logger.info("Shutting down TEOS")

    exit(0)


def get_config(command_line_conf, data_dir):
    """
    Combines the command line config with the config loaded from the file and the default config in order to construct
    the final config object.

    Args:
        command_line_conf (:obj:`dict`): a collection of the command line parameters.

    Returns:
        :obj:`dict`: A dictionary containing all the system's configuration parameters.
    """

    config_loader = ConfigLoader(data_dir, CONF_FILE_NAME, DEFAULT_CONF, command_line_conf)
    config = config_loader.build_config()

    # Set default RPC port if not overwritten by the user.
    if "BTC_RPC_PORT" not in config_loader.overwritten_fields:
        config["BTC_RPC_PORT"] = get_default_rpc_port(config.get("BTC_NETWORK"))

    return config


def main(config):
    global db_manager, chain_monitor

    try:
        signal(SIGINT, handle_signals)
        signal(SIGTERM, handle_signals)
        signal(SIGQUIT, handle_signals)

        setup_data_folder(config.get("DATA_DIR"))
        setup_logging(config.get("LOG_FILE"))

        logger.info("Starting TEOS")

        bitcoind_connect_params = {k: v for k, v in config.items() if k.startswith("BTC_RPC")}
        bitcoind_feed_params = {k: v for k, v in config.items() if k.startswith("BTC_FEED")}

        if not can_connect_to_bitcoind(bitcoind_connect_params):
            logger.error("Cannot connect to bitcoind. Shutting down")

        elif not in_correct_network(bitcoind_connect_params, config.get("BTC_NETWORK")):
            logger.error("bitcoind is running on a different network, check conf.py and bitcoin.conf. Shutting down")

        else:
            if not os.path.exists(config.get("TEOS_SECRET_KEY")) or config.get("OVERWRITE_KEY"):
                logger.info("Generating a new key pair")
                sk = Cryptographer.generate_key()
                Cryptographer.save_key_file(sk.to_der(), "teos_sk", config.get("DATA_DIR"))

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

            # Fire ChainMonitor
            # FIXME: 92-block-data-during-bootstrap-db
            chain_monitor.monitor_chain()

            # Start the internal API
            internal_api = InternalAPI(watcher, INTERNAL_API_ENDPOINT)
            internal_api.rpc_server.start()
            internal_api.logger.info(f"Initialized. Serving at {internal_api.endpoint}")

            # Start the API (using gunicorn) and the RPC server
            # FIXME: We may like to add workers depending on a config value
            subprocess.Popen(
                [
                    "gunicorn",
                    f"--bind={config.get('API_BIND')}:{config.get('API_PORT')}",
                    f"teos.api:serve(internal_api_endpoint='{INTERNAL_API_ENDPOINT}', "
                    f"min_to_self_delay='{config.get('MIN_TO_SELF_DELAY')}', log_file='{config.get('LOG_FILE')}')",
                ]
            )
            Process(
                target=rpc.serve,
                args=(config.get("RPC_BIND"), config.get("RPC_PORT"), INTERNAL_API_ENDPOINT),
                daemon=True,
            ).start()

            # Hang there until a stop command is received
            internal_api.rpc_server.wait_for_termination()

    except Exception as e:
        logger.error("An error occurred: {}. Shutting down".format(e))
        exit(1)


if __name__ == "__main__":
    command_line_conf = {}
    data_dir = DATA_DIR

    try:
        opts, _ = getopt(
            argv[1:],
            "hd",
            [
                "apibind=",
                "apiport=",
                "rpcbind=",
                "rpcport=",
                "btcnetwork=",
                "btcrpcuser=",
                "btcrpcpassword=",
                "btcrpcconnect=",
                "btcrpcport=",
                "btcfeedconnect=",
                "btcfeedport=",
                "datadir=",
                "daemon",
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
            if opt in ["--rpcbind"]:
                command_line_conf["RPC_BIND"] = arg
            if opt in ["--rpcport"]:
                try:
                    command_line_conf["RPC_PORT"] = int(arg)
                except ValueError:
                    exit("rpcport must be an integer")
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
                data_dir = os.path.expanduser(arg)
            if opt in ["-d", "--daemon"]:
                command_line_conf["DAEMON"] = True
            if opt in ["--overwritekey"]:
                command_line_conf["OVERWRITE_KEY"] = True
            if opt in ["-h", "--help"]:
                exit(show_usage())

    except GetoptError as e:
        exit(e)

    config = get_config(command_line_conf, data_dir)

    if config.get("DAEMON"):
        print("Starting TEOS")
        with daemon.DaemonContext():
            main(config)
    else:
        main(config)
