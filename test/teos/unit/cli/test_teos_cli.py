import os
import pytest
import time
import grpc
from grpc_testing import channel, strict_fake_time
from unittest.mock import MagicMock

from common.cryptographer import Cryptographer
from teos.cli.teos_cli import show_usage, CLI, CLICommand
from teos.cli.rpc_client import UserPassCallCredentials
from teos.protobuf import tower_services_pb2 
from common.exceptions import InvalidParameter


@CLI.command
class MockCommandRpcUnreachable(CLICommand):
    """
    NAME:   teos-cli mock_command_rpc_unreachable - A mock command that simulates a network error.
    """

    name = "mock_command_rpc_unreachable"

    @staticmethod
    def run(rpc_client, opts_args):
        # RpcError does not define the code() method, so we mock it in.
        error = grpc.RpcError()
        error.code = lambda: grpc.StatusCode.UNAVAILABLE
        raise error


@CLI.command
class MockCommandRpcError(CLICommand):
    """
    NAME:   teos-cli mock_command_rpc_error - A mock command that simulates some other grpc error.
    """

    name = "mock_command_rpc_error"

    @staticmethod
    def run(rpc_client, opts_args):
        # RpcError does not define the details() method, so we mock it in.
        error = grpc.RpcError()
        error.code = lambda: grpc.StatusCode.INTERNAL
        error.details = lambda: "error details"
        raise error


@CLI.command
class MockCommandInvalidParameter(CLICommand):
    """
    NAME:   teos-cli mock_command_invalid_parameter - A mock command that raises InvalidParameter.
    """

    name = "mock_command_invalid_parameter"

    @staticmethod
    def run(rpc_client, opts_args):
        raise InvalidParameter("Invalid parameter")


@CLI.command
class MockCommandException(CLICommand):
    """
    NAME:   teos-cli mock_command_exception - A mock command that raises some other Exception.
    """

    name = "mock_command_exception"

    @staticmethod
    def run(rpc_client, opts_args):
        raise Exception("Mock Exception")


def return_none(*args, **kwargs):
    return None


def create_test_channel(*args):
    descriptors = tower_services_pb2.DESCRIPTOR.services_by_name.values()
    fake_time = strict_fake_time(time.time()) 
    test_channel = channel(descriptors, fake_time)

    return test_channel


def monkeypatch_rpcclient(monkeypatch, function, func_args):
    for attr in [(Cryptographer, "load_key_file"), (UserPassCallCredentials, "__init__"), (grpc, "metadata_call_credentials"), (grpc, "ssl_channel_credentials"), (grpc, "composite_channel_credentials")]:
        monkeypatch.setattr(attr[0], attr[1], return_none, raising=True)

    monkeypatch.setattr(grpc, "secure_channel", create_test_channel, raising=True)

    result = function(*func_args) 

    return monkeypatch, result


@pytest.fixture
def cli(monkeypatch):
    monkeypatch, cli = monkeypatch_rpcclient(monkeypatch, CLI, [".teos-cli-test", {}])

    # cli = CLI(".teos-cli-test", {})
    yield cli
    os.rmdir(".teos-cli-test")


def test_show_usage_does_not_throw():
    # If any of the Cli commands' docstring has a wrong format and cannot be parsed, this will raise an error
    show_usage()


def test_cli_init_does_not_throw(monkeypatch):
    try:
        monkeypatch, cli = monkeypatch_rpcclient(monkeypatch, CLI, [".teos-cli-test", {}])
    finally:
        os.rmdir(".teos-cli-test")


def test_run_rpcerror_unavailable(cli, monkeypatch):
    assert "It was not possible to reach the Eye of Satoshi" in cli.run("mock_command_rpc_unreachable", [])


def test_run_rpcerror_other(cli, monkeypatch):
    assert "error details" == cli.run("mock_command_rpc_error", [])


def test_run_invalid_parameter(cli, monkeypatch):
    assert "Invalid parameter" in cli.run("mock_command_invalid_parameter", [])


def test_run_exception(cli, monkeypatch):
    assert "Unknown error occurred: Mock Exception" == cli.run("mock_command_exception", [])


def test_unknown_command_exits(cli):
    assert "Unknown command" in cli.run("this_command_probably_doesnt_exist", [])


def test_stop(cli, monkeypatch):
    rpc_client_mock = MagicMock(cli.rpc_client)
    monkeypatch.setattr(cli, "rpc_client", rpc_client_mock)

    cli.run("stop", [])

    rpc_client_mock.stop.assert_called_once()


def test_get_all_appointments(cli, monkeypatch):
    rpc_client_mock = MagicMock(cli.rpc_client)
    monkeypatch.setattr(cli, "rpc_client", rpc_client_mock)

    cli.run("get_all_appointments", [])

    rpc_client_mock.get_all_appointments.assert_called_once()


def test_get_tower_info(cli, monkeypatch):
    rpc_client_mock = MagicMock(cli.rpc_client)
    monkeypatch.setattr(cli, "rpc_client", rpc_client_mock)

    cli.run("get_tower_info", [])

    rpc_client_mock.get_tower_info.assert_called_once()


def test_get_user(cli, monkeypatch):
    rpc_client_mock = MagicMock(cli.rpc_client)
    monkeypatch.setattr(cli, "rpc_client", rpc_client_mock)

    assert "No user_id was given" in cli.run("get_user", [])
    assert "Expected only one argument, not 2" in cli.run("get_user", ["1", "2"])

    # the previous calls should not have called the rpc client, since the arguments number was wrong
    cli.run("get_user", ["42"])
    rpc_client_mock.get_user.assert_called_once_with("42")


def test_get_users(cli, monkeypatch):
    rpc_client_mock = MagicMock(cli.rpc_client)
    monkeypatch.setattr(cli, "rpc_client", rpc_client_mock)

    cli.run("get_users", [])

    rpc_client_mock.get_users.assert_called_once()
