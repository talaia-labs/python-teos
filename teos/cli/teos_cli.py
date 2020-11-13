import os
import sys
from sys import argv
from getopt import getopt, GetoptError
import grpc

from common.config_loader import ConfigLoader
from common.tools import setup_data_folder
from common.exceptions import InvalidParameter

from teos import DEFAULT_CONF, DATA_DIR, CONF_FILE_NAME
from teos.cli.rpc_client import RPCClient


def show_usage():
    """
    Generates the help message shown when teos-cli is called incorrectly, no command was given, or it is called with
    `teos-cli help` or `teos-cli -h`.

    This function iterates the docstring of each registered command, and looks for a line with the format:
       NAME:   teos-cli command_name - One line description of the command called "command_name".
    If such a line is not found, or it is not formatted as above, ``ValueError`` is raised.
    """

    command_help_lines = []
    longest_command_length = max(len(x) for x in CLI.COMMANDS.keys())

    for command_name, command_class in CLI.COMMANDS.items():
        doc = command_class.__doc__

        # find and parse the first line containing NAME:
        name_line = next(line for line in doc.split("\n") if "NAME:" in line)
        if "teos-cli" not in name_line:
            raise ValueError(f"The NAME line of the {command_name} command is malformed")

        _, rest = name_line.split("teos-cli")

        if " - " not in rest:
            raise ValueError(f"The NAME line of the {command_name} command is malformed")

        command_name_in_line, command_description = map(lambda x: x.strip(), rest.split(" - "))

        if command_name_in_line != command_name:
            raise ValueError(f"The NAME line of the {command_name} command is malformed")

        padded_command_name = command_name.ljust(longest_command_length, " ")

        command_help_lines.append(f"\t{padded_command_name}  {command_description}")

    commands_help = "\n".join(command_help_lines)

    return (
        "USAGE: "
        "\n\tteos-cli [global options] command [command options] [arguments]"
        "\n\nCOMMANDS:\n"
        f"{commands_help}"
        "\n\nGLOBAL OPTIONS:"
        "\n\t--rpcconnect  RPC server where to send the requests. Defaults to 'localhost' (modifiable in conf file)."
        "\n\t--rpcport     RPC port where to send the requests. Defaults to '8814' (modifiable in conf file)."
        "\n\t--datadir     Specify data directory used for the config file. Defaults to '~\\.teos'."
        "\n\t-d, --debug   Shows debug information and stores it in teos_cli.log."
        "\n\t-h, --help    Shows this message."
        "\n"
    )


class CLICommand:
    """
    Base class of each CLI command.

    All the implementations should have an appropriately formatted docstring. See existing commands for an example.
    Any implementation _must_ override the ``name`` attribute, and it might override the ``shortopts`` and ``longopts``
    attributes.
    """

    name = None
    shortopts = ""
    longopts = []

    @classmethod
    def parse_args(cls, args):
        """Parses the ``args`` array using ``getopt``, using ``shortopts`` and ``longopts`` as options."""

        return getopt(args, cls.shortopts, cls.longopts)

    @staticmethod
    def run(rpc_client, opts_args):
        """
        Executes the command. Receives as parameters the rpc_client and the output of ``parse_args`` on the command
        arguments.
        """

        raise NotImplementedError()


class CLI:
    """
    This class contains the logic for running all the commands of the command line interface. All the commands must be
    subclasses of :class:`CLICommand` and need to be added to this class using the ``command`` decorator.

    Args:
        data_dir (:obj:`str`): the path to the data directory where the configuration file may be found.
        command_line_conf (:obj:`dict`): the command line settings, parsed in a dictionary.

    Attributes:
        rpc_client (:class:`RpcClient`): the rpc client that is passed to the ``run`` method of the commands.
    """

    # A dictionary mapping each command's name to the corresponding CLICommand subclass.
    # It is populated by the ``command`` decorator.
    COMMANDS = {}

    def __init__(self, data_dir, command_line_conf):
        # Loads config and sets up the data folder and log file
        config_loader = ConfigLoader(data_dir, CONF_FILE_NAME, DEFAULT_CONF, command_line_conf)
        config = config_loader.build_config()

        setup_data_folder(data_dir)

        teos_rpc_host = config.get("RPC_BIND")
        teos_rpc_port = config.get("RPC_PORT")

        self.rpc_client = RPCClient(teos_rpc_host, teos_rpc_port)

    @classmethod
    def command(cls, command_cls):
        """
        Decorator used to register a new command, which must be a subclass of :class:`CLICommand` and must override
        the ``name`` field with an appropriate string.

        Raises:
            :obj:`TypeError`: ``command_cls`` is not a subclass of :class:`CLICommand`, or its ``name`` field is not a
            string.
        """

        if not issubclass(command_cls, CLICommand):
            raise TypeError(f"{command_cls.__name__} is not a subclass of CLICommand")

        if not isinstance(command_cls.name, str):
            raise TypeError(f'The "name" attribute of {command_cls.__name__} must be a string.')

        cls.COMMANDS[command_cls.name] = command_cls
        return command_cls

    def run(self, command_name, raw_args):
        """
        Parses ``raw_args`` using the ``parse_args`` method of the command.
        Then, executes the command's ``run`` method, passing the ``rpc_client`` and the output of ``parse_args`` to it.
        If any error is raised by the command, returns an error message.

        Returns:
            :obj:`str`: The return value of the ``run`` method of the command or an error message.
        """

        if command_name not in self.COMMANDS:
            return "Unknown command. Use help to check the list of available commands"

        command = self.COMMANDS[command_name]

        try:
            args = command.parse_args(raw_args)
            return command.run(self.rpc_client, args)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                return "It was not possible to reach the Eye of Satoshi. Are you sure the tower is running?"
            else:
                return e.details()
        except InvalidParameter as e:
            error_message = e.msg if not e.kwargs else f"{e.msg}. Error arguments: {e.kwargs}"
            return error_message + "\n\n" + show_usage()
        except Exception as e:
            return f"Unknown error occurred: {str(e)}"


@CLI.command
class GetAllAppointmentsCommand(CLICommand):
    """
    NAME:   teos-cli get_all_appointments - Gets information about all the appointments stored in the tower.

    USAGE:  teos-cli get_all_appointments

    DESCRIPTION:

        Gets information about all appointments stored in the tower.
    """

    name = "get_all_appointments"

    @staticmethod
    def run(rpc_client, opts_args):
        return rpc_client.get_all_appointments()


@CLI.command
class GetTowerInfoCommand(CLICommand):
    """
    NAME:   teos-cli get_tower_info - Gets generic information about the tower.

    USAGE:  teos-cli get_tower_info

    DESCRIPTION:

        Gets generic information about the tower, like tower_id and aggregate data on users and appointments.
    """

    name = "get_tower_info"

    @staticmethod
    def run(rpc_client, opts_args):
        return rpc_client.get_tower_info()


@CLI.command
class GetUsersCommand(CLICommand):
    """
    NAME:   teos-cli get_users - Gets the list of registered user ids.

    USAGE:  teos-cli get_users

    DESCRIPTION:

        Gets an array with the user ids of all the users registered to the tower.
    """

    name = "get_users"

    @staticmethod
    def run(rpc_client, opts_args):
        return rpc_client.get_users()


@CLI.command
class GetUserCommand(CLICommand):
    """
    NAME:   teos-cli get_user - Gets information about a specific user.

    USAGE:  teos-cli get_user "user_id"

    DESCRIPTION:

        Gets information about a specific user.
    """

    name = "get_user"

    @staticmethod
    def run(rpc_client, opts_args):
        opts, args = opts_args

        if not args:
            raise InvalidParameter("No user_id was given")
        if len(args) > 1:
            raise InvalidParameter(f"Expected only one argument, not {len(args)}")

        return rpc_client.get_user(args[0])


@CLI.command
class StopCommand(CLICommand):
    """
    NAME:   teos-cli stop - Requests a graceful shutdown of the tower..

    USAGE:  teos-cli stop

    DESCRIPTION:

        Requests a graceful shutdown of the tower.
    """

    name = "stop"

    @staticmethod
    def run(rpc_client, opts_args):
        rpc_client.stop()
        return "Closing the Eye of Satoshi"


@CLI.command
class HelpCommand(CLICommand):
    """
    NAME:   teos-cli help - Shows general help, or help for a specific command.

    USAGE:  teos-cli help [command]

    DESCRIPTION:

        Shows a summary of all the commands and global options. If command is given, shows detailed help for the
        command.
    """

    name = "help"

    @staticmethod
    def run(rpc_client, opts_args):
        opts, args = opts_args

        if not args:
            return show_usage()
        elif len(args) > 1:
            return f"Expected only one argument, not {len(args)}"

        command_name = args.pop(0)
        if command_name not in CLI.COMMANDS:
            return "Unknown command."

        return CLI.COMMANDS[command_name].__doc__


def run():
    # Split the command line as follows: global options, command, command args,
    # where command is the first argument not starting with "-".

    try:
        command_index = next(i for i in range(len(argv)) if i > 0 and not argv[i].startswith("-"))
    except StopIteration:
        sys.exit(show_usage())

    command = argv[command_index]
    global_options = argv[1:command_index]
    command_args = argv[command_index + 1 :]

    command_line_conf = {}

    # Process global options
    try:
        opts, args = getopt(global_options, "h", ["rpcbind=", "rpcport=", "datadir=", "help"])

        data_dir = DATA_DIR

        for opt, arg in opts:
            if opt in ["--rpcbind"]:
                if arg:
                    command_line_conf["RPC_BIND"] = arg

            if opt in ["--rpcport"]:
                if arg:
                    try:
                        command_line_conf["RPC_PORT"] = int(arg)
                    except ValueError:
                        sys.exit("port must be an integer")

            if opt in ["--datadir"]:
                data_dir = os.path.expanduser(arg)

            if opt in ["-h", "--help"]:
                sys.exit(show_usage())
    except GetoptError as e:
        sys.exit("{}".format(e))

    if command in CLI.COMMANDS:
        cli = CLI(data_dir, command_line_conf)
        result = cli.run(command, command_args)
        if result:
            print(result)
    elif not command:
        sys.exit("No command provided. Use help to check the list of available commands")
    else:
        sys.exit("Unknown command. Use help to check the list of available commands")


if __name__ == "__main__":
    run()
