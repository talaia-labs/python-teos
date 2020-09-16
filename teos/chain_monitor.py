from enum import Enum
from queue import Queue
import zmq
from threading import Thread, Event, Condition

from teos.logger import get_logger


class ChainMonitorStatus(Enum):
    IDLE = 0
    LISTENING = 1
    ACTIVE = 2
    TERMINATED = 3


class ChainMonitor:
    """
    The :obj:`ChainMonitor` is in charge of monitoring the blockchain (via ``bitcoind``) to detect new blocks on top
    of the best chain. If a new best block is spotted, the chain monitor will notify the given queues.

    The :obj:`ChainMonitor` monitors the chain using two methods: ``zmq`` and ``polling``. Blocks are only notified
    once per queue and the notification is triggered by the method that detects the block faster.

    The :obj:`ChainMonitor` lifecycle goes through 4 states: idle, listening, active and terminated.
    When a :obj:`ChainMonitor` instance is created, it is not yet monitoring the chain and the ``status`` attribute
    is set to ``ChainMonitorStatus.IDLE``.
    Once the ``monitor_chain`` method is called, the chain monitor changes ``status`` to
    ``ChainMonitorStatus.LISTENING``, and starts monitoring the chain for new blocks; it does not yet notify the
    receiving queues, but keeps the block hashes in the order they where spotted in an internal queue.
    Once the ``activate`` method is called, the ``status`` changes to ``ChainMonitorStatus.ACTIVE``, and the receiving
    queues are notified in order for all the block hashes that are in the internal queue or any new one that is
    detected.
    Finally, once the ``terminate`` method is called, the ``status`` is changed to ``ChainMonitorStatus.TERMINATED``,
    the chain monitor stops monitoring the chain and no receiving queue will be notified about new blocks (including
    any block that is currently in the internal queue). A final ``ChainMonitor.END_MESSAGE`` is sent to all the
    subscribers.

    Args:
        receiving_queues (:obj:`list`): a list of :obj:`Queue` objects that will be notified when the chain_monitor is
            active and it received new blocks hashes.
        block_processor (:obj:`BlockProcessor <teos.block_processor.BlockProcessor>`): a :obj:`BlockProcessor` instance.
        bitcoind_feed_params (:obj:`dict`): a dict with the feed (ZMQ) connection parameters.

    Attributes:
        logger (:obj:`Logger <teos.logger.Logger>`): The logger for this component.
        last_tips (:obj:`list`): A list of last chain tips. Used as a sliding window to avoid notifying about old tips.
        check_tip (:obj:`Event`): An event that is triggered at fixed time intervals and controls the polling thread.
        lock (:obj:`Condition`): A lock used to protect concurrent access to the queues by the zmq and polling threads.
        zmqSubSocket (:obj:`socket`): A socket to connect to ``bitcoind`` via ``zmq``.
        polling_delta (:obj:`int`): Time between polls (in seconds).
        max_block_window_size (:obj:`int`): Max size of ``last_tips``.
        queue (:obj:`Queue`): A queue where blocks are stored before they are processed.
        status (:obj:`ChainMonitorStatus`): The current status of the monitor, either ``ChainMonitorStatus.IDLE``,
            ``ChainMonitorStatus.LISTENING``, ``ChainMonitorStatus.ACTIVE`` or ``ChainMonitorStatus.TERMINATED``.
    """

    END_MESSAGE = "END"

    def __init__(self, receiving_queues, block_processor, bitcoind_feed_params):
        self.logger = get_logger(component=ChainMonitor.__name__)
        self.last_tips = []

        self.check_tip = Event()
        self.lock = Condition()

        self.zmqContext = zmq.Context()
        self.zmqSubSocket = self.zmqContext.socket(zmq.SUB)
        self.zmqSubSocket.setsockopt(zmq.RCVHWM, 0)
        self.zmqSubSocket.setsockopt_string(zmq.SUBSCRIBE, "hashblock")
        self.zmqSubSocket.connect(
            "%s://%s:%s"
            % (
                bitcoind_feed_params.get("BTC_FEED_PROTOCOL"),
                bitcoind_feed_params.get("BTC_FEED_CONNECT"),
                bitcoind_feed_params.get("BTC_FEED_PORT"),
            )
        )

        self.receiving_queues = receiving_queues

        self.polling_delta = 60
        self.max_block_window_size = 10
        self.block_processor = block_processor
        self.queue = Queue()
        self.status = ChainMonitorStatus.IDLE

    def enqueue(self, block_hash):
        """
        Adds a new block hash to the internal queue of the  :obj:`ChainMonitor` and the internal state. The state contains
        the list of ``last_tips`` to prevent notifying about old blocks. ``last_tips`` is bounded to
        ``max_block_window_size``.

        Args:
            block_hash (:obj:`str`): the new best tip.

        Returns:
            :obj:`bool`: True if the state was successfully updated, False otherwise.
        """

        if block_hash not in self.last_tips:
            with self.lock:
                self.queue.put(block_hash)
                self.last_tips.append(block_hash)

                if len(self.last_tips) > self.max_block_window_size:
                    self.last_tips.pop(0)

            return True

        else:
            return False

    def monitor_chain_polling(self):
        """
        Monitors ``bitcoind`` via polling. Once the method is fired, it keeps monitoring as long as the ``status``
        attribute is not ``ChainMonitorStatus.TERMINATED``. Polling is performed once every ``polling_delta`` seconds.
        If a new best tip is found, it is added to the internal queue.
        """

        while self.status != ChainMonitorStatus.TERMINATED:
            self.check_tip.wait(timeout=self.polling_delta)

            current_tip = self.block_processor.get_best_block_hash()

            # get_best_block_hash may return None if the RPC times out.
            if current_tip and current_tip not in self.last_tips:
                self.logger.info("New block received via polling", block_hash=current_tip)
                self.enqueue(current_tip)

    def monitor_chain_zmq(self):
        """
        Monitors ``bitcoind`` via zmq. Once the method is fired, it keeps monitoring as long as the ``status``
        attribute is not ``ChainMonitorStatus.TERMINATED``. If a new best tip is found, it is added to the internal
        queue.
        """

        while self.status != ChainMonitorStatus.TERMINATED:
            msg = self.zmqSubSocket.recv_multipart()

            topic = msg[0]
            body = msg[1]

            if topic == b"hashblock":
                block_hash = body.hex()
                if block_hash not in self.last_tips:
                    self.logger.info("New block received via zmq", block_hash=block_hash)
                    self.enqueue(block_hash)

    def notify_subscribers(self):
        """
        Once the method is fired, it keeps getting the elements added to the internal queue and notifies the receiving
        queues about them. It terminates whenever the internal state is set to ``ChainMonitorStatus.TERMINATED``.
        """

        while self.status != ChainMonitorStatus.TERMINATED:
            message = self.queue.get()
            # A special ChainMonitor.END_MESSAGE is added to the queue after the status is set to TERMINATED
            # In all the other cases, message is a block_hash
            with self.lock:
                for rec_queue in self.receiving_queues:
                    rec_queue.put(message)

    def monitor_chain(self):
        """
        Changes the ``status`` of the :obj:`ChainMonitor` from idle to listening. It initializes the ``last_tips`` list
        to terminate the current best tip (by querying the :obj:`BlockProcessor <teos.block_processor.BlockProcessor>`)
        and creates two threads, one per each monitoring approach (``zmq`` and ``polling``).

        Raises:
            :obj:`RuntimeError`: if the ``status`` was not ``ChainMonitorStatus.IDLE`` when the method was called.
        """

        if self.status != ChainMonitorStatus.IDLE:
            raise RuntimeError(f"This method can only be called in IDLE status. Current status is {self.status.name}.")

        self.status = ChainMonitorStatus.LISTENING

        self.last_tips.append(self.block_processor.get_best_block_hash())
        Thread(target=self.monitor_chain_polling, daemon=True).start()
        Thread(target=self.monitor_chain_zmq, daemon=True).start()

    def activate(self):
        """
        Changes the ``status`` of the :obj:`ChainMonitor` from listening to active. It creates a new thread that runs
        the ``notify_subscribers`` method, which is in charge of notifying the receiving queue for each block hash that
        is added to the internal queue.

        Raises:
            :obj:`RuntimeError`: if the ``status`` was not ``ChainMonitorStatus.LISTENING`` when the method was called.
        """

        if self.status != ChainMonitorStatus.LISTENING:
            raise RuntimeError(
                f"This method can only be called in LISTENING status. Current status is {self.status.name}."
            )
        self.status = ChainMonitorStatus.ACTIVE
        Thread(target=self.notify_subscribers, daemon=True).start()

    def terminate(self):
        """
        Changes the ``status`` of the :obj:`ChainMonitor` to terminated and sends the ``ChainMonitor.END_MESSAGE``
        message to the internal queue. All the threads will stop as soon as possible.
        """

        self.status = ChainMonitorStatus.TERMINATED
        self.queue.put(ChainMonitor.END_MESSAGE)
