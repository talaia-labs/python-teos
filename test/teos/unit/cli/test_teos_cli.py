import os
import pytest
import grpc
from unittest.mock import MagicMock

from teos.cli.teos_cli import show_usage, CLI, CLICommand
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


@pytest.fixture
def cli():
    cli = CLI(".teos-cli-test", {})
    yield cli
    os.rmdir(".teos-cli-test")


def test_show_usage_does_not_throw():
    # If any of the Cli commands' docstring has a wrong format and cannot be parsed, this will raise an error
    show_usage()


def test_cli_init_does_not_throw():
    try:
        CLI(".teos-cli-test", {})
    finally:
        os.rmdir(".teos-cli-test")


def test_run_rpcerror_unavailable(cli, monkeypatch):
    assert "It was not possible to reach the Eye of Satoshi" in cli.run("mock_command_rpc_unreachable", [])


def test_run_rpcerror_other(cli, monkeypatch):
    assert "error details" == cli.run("mock_command_rpc_error", [])


def test_run_invalid_parameter(cli, monkeypatch):
    assert "Invalid parameter" == cli.run("mock_command_invalid_parameter", [])


def test_run_exception(cli, monkeypatch):
    assert "Unknown error occurred: Mock Exception" == cli.run("mock_command_exception", [])


def test_get_tower_info(cli, monkeypatch):
    rpc_client_mock = MagicMock(cli.rpc_client)
    monkeypatch.setattr(cli, "rpc_client", rpc_client_mock)

    cli.run("get_tower_info", [])

    rpc_client_mock.get_tower_info.assert_called_once()


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

    assert cli.run("get_user", []) == "No user_id was given"
    assert cli.run("get_user", ["1", "2"]) == "Expected only one argument, not 2"

    # the previous calls should not have called the rpc client, since the arguments number was wrong
    cli.run("get_user", ["42"])
    rpc_client_mock.get_user.assert_called_once_with("42")


def test_get_users(cli, monkeypatch):
    rpc_client_mock = MagicMock(cli.rpc_client)
    monkeypatch.setattr(cli, "rpc_client", rpc_client_mock)

    cli.run("get_users", [])

    rpc_client_mock.get_users.assert_called_once()
