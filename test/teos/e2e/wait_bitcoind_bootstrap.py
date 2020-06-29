from time import sleep

from test.teos.e2e.conftest import get_config
from teos.utils.auth_proxy import AuthServiceProxy, JSONRPCException
from teos import DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF

# Wait until the node has finished bootstrapping
config = get_config(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF)
bitcoin_cli = AuthServiceProxy(
    "http://%s:%s@%s:%d"
    % (
        config.get("BTC_RPC_USER"),
        config.get("BTC_RPC_PASSWORD"),
        config.get("BTC_RPC_CONNECT"),
        config.get("BTC_RPC_PORT"),
    )
)

while True:
    try:
        new_addr = bitcoin_cli.getnewaddress()
        break
    except JSONRPCException as e:
        if "error code: -28" in str(e):
            sleep(1)
