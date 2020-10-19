import pytest

from teos.cli.rpc_client import RPCClient
from common.exceptions import InvalidParameter

test_host = "test"
test_port = 4242


@pytest.fixture
def rpc_client():
    return RPCClient(test_host, test_port)


def test_get_user_invalid_user_id(rpc_client):
    with pytest.raises(InvalidParameter):
        rpc_client.get_user("1234")  # invalid user_id
