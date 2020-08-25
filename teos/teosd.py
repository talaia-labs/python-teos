import os
import daemon
import subprocess
from sys import argv, exit
import multiprocessing
import threading

from getopt import getopt, GetoptError
from signal import signal, SIGINT, SIGQUIT, SIGTERM

from common.logger import setup_logging, get_logger
from common.config_loader import ConfigLoader
from common.cryptographer import Cryptographer
from common.tools import setup_data_folder

import teos.api as api
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
from teos.constants import INTERNAL_API_ENDPOINT, SHUTDOWN_GRACE_TIME

logger = get_logger(component="Daemon")
parent_pid = os.getpid()


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


class TeosDaemon:
    """
    The :class:`TeosDaemon` organizes the code to initialize all the components of teos, start the service, stop and
    teardown.

    Args:
        config (:obj:`dict`): the configuration object.

    Attributes:
        stop_command_event (:obj:`threading.Event`) the Event that will be set to initiate a graceful shutdown.
        stop_event (:obj:`multiprocessing.Event`) the Event that services running on different processes will monitor
            in order to be informed that they should shutdown.
        block_processor (:obj:`teos.block_processor.BlockProcessor`) the BlockProcessor instance.
        db_manager (:obj:`teos.appointments_dbm.AppointmentsDBM`) the db manager for appointments.
        watcher (:obj:`teos.watcher.Watcher`) the `Watcher` instance.
        chain_monitor (:obj:`teos.chain_monitor.ChainMonitor`) the ``ChainMonitor`` instance.
        self.api_popen (:obj:`subprocess.Popen` or :obj:`None`) if set, the ``Popen`` instance running the public API.
        self.api_process (:obj:`multiprocessing.Process` or :obj:`None`) if set, the ``Process`` instance running the
            public API.
        self.rpc_process (:obj:`multiprocessing.Process`) the instance of the internal RPC server; only set if running.
        self.internal_api (:obj:`teos.internal_api.InternalAPI`) the InternalAPI instance.
    """

    def __init__(self, config):
        self.config = config

        # event triggered when a ``stop`` command is issued
        # Using multiprocessing.Event seems to cause a deadlock if event.set() is called in a signal handler that
        # interrupted event.wait(). This does not happen with threading.Event.
        # See https://bugs.python.org/issue41606
        self.stop_command_event = threading.Event()

        # event triggered when the public API is halted, hence teosd is ready to stop
        self.stop_event = multiprocessing.Event()

        setup_data_folder(self.config.get("DATA_DIR"))
        setup_logging(self.config.get("LOG_FILE"))

        bitcoind_connect_params = {k: v for k, v in self.config.items() if k.startswith("BTC_RPC")}
        bitcoind_feed_params = {k: v for k, v in self.config.items() if k.startswith("BTC_FEED")}

        if not can_connect_to_bitcoind(bitcoind_connect_params):
            raise RuntimeError("Cannot connect to bitcoind")

        elif not in_correct_network(bitcoind_connect_params, self.config.get("BTC_NETWORK")):
            raise RuntimeError("bitcoind is running on a different network, check teos.conf and bitcoin.conf")

        if not os.path.exists(self.config.get("TEOS_SECRET_KEY")) or self.config.get("OVERWRITE_KEY"):
            logger.info("Generating a new key pair")
            sk = Cryptographer.generate_key()
            Cryptographer.save_key_file(sk.to_der(), "teos_sk", self.config.get("DATA_DIR"))

        else:
            logger.info("Tower identity found. Loading keys")
            secret_key_der = Cryptographer.load_key_file(self.config.get("TEOS_SECRET_KEY"))

            if not secret_key_der:
                raise IOError("TEOS private key cannot be loaded")
            sk = Cryptographer.load_private_key_der(secret_key_der)

        logger.info("tower_id = {}".format(Cryptographer.get_compressed_pk(sk.public_key)))
        self.block_processor = BlockProcessor(bitcoind_connect_params)
        carrier = Carrier(bitcoind_connect_params)

        gatekeeper = Gatekeeper(
            UsersDBM(self.config.get("USERS_DB_PATH")),
            self.block_processor,
            self.config.get("SUBSCRIPTION_SLOTS"),
            self.config.get("SUBSCRIPTION_DURATION"),
            self.config.get("EXPIRY_DELTA"),
        )
        self.db_manager = AppointmentsDBM(self.config.get("APPOINTMENTS_DB_PATH"))
        responder = Responder(self.db_manager, gatekeeper, carrier, self.block_processor)
        self.watcher = Watcher(
            self.db_manager,
            gatekeeper,
            self.block_processor,
            responder,
            sk,
            self.config.get("MAX_APPOINTMENTS"),
            self.config.get("LOCATOR_CACHE_SIZE"),
        )

        # Create the chain monitor and start monitoring the chain
        self.chain_monitor = ChainMonitor(
            self.watcher.block_queue, self.watcher.responder.block_queue, self.block_processor, bitcoind_feed_params
        )

        # Set up the internal API
        self.internal_api = InternalAPI(self.watcher, INTERNAL_API_ENDPOINT, self.stop_command_event)

        # Create the rpc, without starting it
        self.rpc_process = multiprocessing.Process(
            target=rpc.serve,
            args=(self.config.get("RPC_BIND"), self.config.get("RPC_PORT"), INTERNAL_API_ENDPOINT, self.stop_event),
            daemon=True,
        )

        # One of this variables will contain the handle of the process running the API, when the service is started
        self.api_popen = None
        self.api_process = None

    def start(self):
        """This method implements the whole lifetime cycle of the the TEOS tower. This method does not return."""
        logger.info("Starting TEOS")
        self.setup_components()
        self.start_services()

        self.stop_command_event.wait()

        self.teardown()

    def setup_components(self):
        """Performs the initial setup and creates all the components."""
        watcher_appointments_data = self.db_manager.load_watcher_appointments()
        responder_trackers_data = self.db_manager.load_responder_trackers()

        if len(watcher_appointments_data) == 0 and len(responder_trackers_data) == 0:
            logger.info("Fresh bootstrap")

            self.watcher.awake()
            self.watcher.responder.awake()

        else:
            logger.info("Bootstrapping from backed up data")

            # Update the Watcher backed up data if found.
            if len(watcher_appointments_data) != 0:
                self.watcher.appointments, self.watcher.locator_uuid_map = Builder.build_appointments(
                    watcher_appointments_data
                )

            # Update the Responder with backed up data if found.
            if len(responder_trackers_data) != 0:
                self.watcher.responder.trackers, self.watcher.responder.tx_tracker_map = Builder.build_trackers(
                    responder_trackers_data
                )

            # Awaking components so the states can be updated.
            self.watcher.awake()
            self.watcher.responder.awake()

            last_block_watcher = self.db_manager.load_last_block_hash_watcher()
            last_block_responder = self.db_manager.load_last_block_hash_responder()

            # Populate the block queues with data if they've missed some while offline. If the blocks of both match
            # we don't perform the search twice.

            # FIXME: 32-reorgs-offline dropped txs are not used at this point.
            last_common_ancestor_watcher, dropped_txs_watcher = self.block_processor.find_last_common_ancestor(
                last_block_watcher
            )
            missed_blocks_watcher = self.block_processor.get_missed_blocks(last_common_ancestor_watcher)

            if last_block_watcher == last_block_responder:
                dropped_txs_responder = dropped_txs_watcher
                missed_blocks_responder = missed_blocks_watcher

            else:
                last_common_ancestor_responder, dropped_txs_responder = self.block_processor.find_last_common_ancestor(
                    last_block_responder
                )
                missed_blocks_responder = self.block_processor.get_missed_blocks(last_common_ancestor_responder)

            # If only one of the instances needs to be updated, it can be done separately.
            if len(missed_blocks_watcher) == 0 and len(missed_blocks_responder) != 0:
                Builder.populate_block_queue(self.watcher.responder.block_queue, missed_blocks_responder)
                self.watcher.responder.block_queue.join()

            elif len(missed_blocks_responder) == 0 and len(missed_blocks_watcher) != 0:
                Builder.populate_block_queue(self.watcher.block_queue, missed_blocks_watcher)
                self.watcher.block_queue.join()

            # Otherwise they need to be updated at the same time, block by block
            elif len(missed_blocks_responder) != 0 and len(missed_blocks_watcher) != 0:
                Builder.update_states(self.watcher, missed_blocks_watcher, missed_blocks_responder)

        # Fire ChainMonitor
        # FIXME: 92-block-data-during-bootstrap-db
        self.chain_monitor.monitor_chain()

    def start_services(self):
        """Readies the tower by setting up signal handling, and starting all the services."""
        signal(SIGINT, self.handle_signals)
        signal(SIGTERM, self.handle_signals)
        signal(SIGQUIT, self.handle_signals)

        # Start the internal API
        self.internal_api.rpc_server.start()
        logger.info(f"Internal API initialized. Serving at {INTERNAL_API_ENDPOINT}")

        # Start the rpc process
        self.rpc_process.start()

        # Start the public API server
        api_endpoint = f"{self.config.get('API_BIND')}:{self.config.get('API_PORT')}"
        if self.config.get("WSGI") == "gunicorn":
            # FIXME: We may like to add workers depending on a config value
            self.api_popen = subprocess.Popen(
                [
                    "gunicorn",
                    f"--bind={api_endpoint}",
                    f"teos.api:serve(internal_api_endpoint='{INTERNAL_API_ENDPOINT}', "
                    f"endpoint='{api_endpoint}', min_to_self_delay='{self.config.get('MIN_TO_SELF_DELAY')}', "
                    f"log_file='{self.config.get('LOG_FILE')}')",
                ]
            )
        else:
            self.api_process = multiprocessing.Process(
                target=api.serve,
                kwargs={
                    "internal_api_endpoint": INTERNAL_API_ENDPOINT,
                    "endpoint": api_endpoint,
                    "min_to_self_delay": self.config.get("MIN_TO_SELF_DELAY"),
                    "log_file": self.config.get("LOG_FILE"),
                    "auto_run": True,
                },
            )
            self.api_process.start()

    def handle_signals(self, signum, frame):
        """Handles signals by initiating a graceful shutdown."""
        logger.info(f"Signal {signum} received. Stopping")

        self.stop_command_event.set()

    def teardown(self):
        """Shuts down all services and closes the DB, then exits. This method does not return."""
        logger.info("Terminating public API")

        # Stop the public API first
        if self.api_popen:
            self.api_popen.terminate()
            self.api_popen.wait()
        else:
            # FIXME: when the public API process is ran with flask, there is no SIGTERM handler attempting
            # a graceful shutdown (rejecting new requests, trying to complete ongoing ones); therefore, we send
            # a SIGKILL instead.
            self.api_process.kill()
            self.api_process.join()

        logger.info("Terminated public API")

        # Signals readiness to shutdown to the other processes
        self.stop_event.set()

        # wait for RPC process to shutdown
        self.rpc_process.join()

        # Stops the internal API, after waiting for some grace time
        logger.info("Internal API stopping")
        self.internal_api.rpc_server.stop(SHUTDOWN_GRACE_TIME).wait()
        logger.info("Internal API stopped")

        # terminate the ChainMonitor
        self.chain_monitor.terminate = True

        logger.info("Closing connection with appointments db")
        self.db_manager.db.close()

        logger.info("Shutting down TEOS")
        exit(0)


def main(config):
    try:
        TeosDaemon(config).start()
    except Exception as e:
        logger.error("An error occurred: {}. Shutting down".format(e))
        exit(1)


if __name__ == "__main__":
    command_line_conf = {}
    data_dir = DATA_DIR

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
            "wsgi=",
            "daemon",
            "overwritekey",
            "help",
        ],
    )
    try:
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
            if opt in ["--wsgi"]:
                if arg in ["gunicorn", "flask"]:
                    command_line_conf["WSGI"] = arg
                else:
                    exit("wsgi must be either gunicorn or flask")
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
