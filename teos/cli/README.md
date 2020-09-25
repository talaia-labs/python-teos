# teos_cli

`teos_cli` is a command line interface to interact with the Eye of Satoshi watchtower server, written in Python3.

## Usage

	teos_cli [global options] command [command options] [arguments]
	
#### Global options

- `--rpcbind`:	API server where to send the requests. Defaults to 'localhost' (modifiable in conf file).
- `--rpcport`:	API port where to send the requests. Defaults to '9814' (modifiable in conf file).
- `-h --help`:	shows a list of commands or help for a specific command.

#### Commands

The command line interface has, currently, the following commands:

- `get_all_appointments`: returns a list of all the appointments currently in the watchtower.
- `get_tower_info`: gets generic information about the tower.
- `get_users`: gets the list of registered user ids.
- `get_user`: gets information about a specific user.
- `help`: shows a list of commands or help for a specific command.

Run `teos_cli help <command>` for detailed information about each command and its arguments.