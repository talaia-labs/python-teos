import pytest

from teos.cli.rpc_client import RPCClient
from common.exceptions import InvalidParameter

from test.teos.unit.cli.test_teos_cli import monkeypatch_rpcclient


test_host = "test"
test_port = 4242
test_cert_path = ""
test_user = "user"
test_pass = "pass"


@pytest.fixture
def rpc_client(monkeypatch):
    monkeypatch, rpc_client = monkeypatch_rpcclient(monkeypatch, RPCClient, [test_host, test_port, test_cert_path, test_user, test_pass])

    return rpc_client


def test_get_user_invalid_user_id(rpc_client):
    with pytest.raises(InvalidParameter):
        rpc_client.get_user("1234")  # invalid user_id
