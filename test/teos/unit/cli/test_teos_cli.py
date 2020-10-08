import os
import pytest
from unittest.mock import MagicMock

from teos.cli.teos_cli import show_usage, CLI


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


def test_unknown_command_exits(cli):
    with pytest.raises(SystemExit):
        cli.run("this_command_probably_doesnt_exist", [])


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

    with pytest.raises(SystemExit):
        # not enough arguments
        cli.run("get_user", [])

    with pytest.raises(SystemExit):
        # too many arguments
        cli.run("get_user", ["1", "2"])

    cli.run("get_user", ["42"])

    rpc_client_mock.get_user.assert_called_once_with("42")


def test_get_users(cli, monkeypatch):
    rpc_client_mock = MagicMock(cli.rpc_client)
    monkeypatch.setattr(cli, "rpc_client", rpc_client_mock)

    cli.run("get_users", [])

    rpc_client_mock.get_users.assert_called_once()
