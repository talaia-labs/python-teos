import time
import random
from threading import Thread
from pyln.proto.wire import LightningServerSocket, PrivateKey

from common.logger import get_logger
from common.exceptions import BasicException
from common.cryptographer import Cryptographer
from common.net.bolt1 import Message, InitMessage, ErrorMessage, PingMessage, PongMessage, UnknownMessageType


PING_INTERVAL = 60


class MisbehavingPeer(BasicException):
    """Raised when a peer misbehaves and the connection needs to be dropped"""

    pass


class PeerConnection:
    def __init__(self, wire, address, logger):
        self.logger = logger
        self.address = address
        self.wire = wire
        self.pending_pongs = []
        self.active = True

        # Start serving
        # FIXME: Add a meaningful init
        self.logger.info(f"New connection accepted from {self.address}")
        self.wire.send_message(InitMessage.from_bytes(b"\x00\x10\x00\x00\x00\x00").serialize())
        Thread(target=self.serve).start()
        Thread(target=self.keep_alive).start()

    def serve(self):
        while self.active:
            try:
                wire_message = self.wire.read_message()
                message = Message.from_bytes(wire_message)

                if isinstance(message, ErrorMessage):
                    self.logger.info("Received error message from peer", msg=message.data, address=self.address)
                if isinstance(message, PingMessage):
                    self.logger.info("Received ping from peer", address=self.address)
                    response = PongMessage(ignored_bytes=bytes(message.num_pong_bytes))
                    self.logger.info("Sending pong", address=self.address)
                    self.wire.send_message(response.serialize())
                if isinstance(message, PongMessage):
                    self.logger.info("Received pong from peer", address=self.address)
                    if self.pending_pongs:
                        ping_message = self.pending_pongs.pop(0)
                        if len(message.ignored_bytes) != ping_message.num_pong_bytes:
                            raise MisbehavingPeer("Peer sent wrong pong. Terminating connection", address=self.address)
                    else:
                        raise MisbehavingPeer("Received pong without sending ping. Disconnecting", address=self.address)

            except (MisbehavingPeer, ValueError) as e:
                self.active = False
                self.logger.info(e.msg, **e.kwargs)
                self.wire.connection.close()
            except UnknownMessageType as e:
                self.logger.info("Unknown message received from peer", address=self.address)
            except OSError:
                self.active = False
                self.logger.info("The connection was dropped by the peer", address=self.address)

    def keep_alive(self):
        while self.active:
            try:
                # Send ping
                expected_pong_bytes = random.randint(0, pow(2, 16) - 1)
                ignored_bytes = bytes(random.randint(0, pow(2, 16) - 4))
                ping_msg = PingMessage(expected_pong_bytes, ignored_bytes)
                self.wire.send_message(ping_msg.serialize())
                self.logger.info(f"Ping sent to {self.address}")
                self.pending_pongs.append(ping_msg)
                time.sleep(PING_INTERVAL)
            except OSError:
                self.logger.info("Lost connection to the peer", address=self.address)


class LightningServer:
    def __init__(self, sk, host, port):
        self.logger = get_logger(component=LightningServer.__name__)
        self.sk = PrivateKey(sk.secret)
        self.id = Cryptographer.get_compressed_pk(sk.public_key)
        self.host = host
        self.port = port
        self.socket = LightningServerSocket(self.sk)

    def serve(self):
        self.socket.bind((self.host, self.port))
        self.logger.info(f"Initialized. Serving at {self.host}:{self.port}", tower_id=self.id)

        while True:
            self.socket.listen()
            wire, address = self.socket.accept()
            PeerConnection(wire, f"{address[0]}:{address[1]}", self.logger)
