import os
from flask import Flask
from flask_jsonrpc import JSONRPC

from common.logger import get_logger


class RPC:
    """
    The :class:`RPC` exposes admin functionality of the watchtower.

    Args:
        host (:obj:`str`): the hostname to listen on.
        port (:obj:`int`): the port of the webserver.
        inspector (:obj:`Inspector <teos.inspector.Inspector>`): an ``Inspector`` instance to check the correctness of
            the received appointment data.
        watcher (:obj:`Watcher <teos.watcher.Watcher>`): a ``Watcher`` instance to pass the requests to.

    Attributes:
        logger: the logger for this component.
    """

    def __init__(self, host, port, inspector, watcher):
        app = Flask(__name__)
        jsonrpc = JSONRPC(app, "/rpc", enable_web_browsable_api=True)
        self.app = app
        self.jsonrpc = jsonrpc

        self.logger = get_logger(component=RPC.__name__)

        self.host = host
        self.port = port
        self.inspector = inspector
        self.watcher = watcher
        self.logger.info("Initialized")

        @jsonrpc.method("echo")
        def echo(msg: str) -> str:
            return msg

    def start(self):
        """ This function starts the Flask server used to run the RPC """
        # Disable flask initial messages
        os.environ["WERKZEUG_RUN_MAIN"] = "true"

        self.app.run(host=self.host, port=self.port)
