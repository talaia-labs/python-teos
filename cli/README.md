# teos_cli

`teos_cli` is a command line interface to interact with the Eye of Satoshi watchtower server, written in Python3.

## Dependencies
Refer to [DEPENDENCIES.md](DEPENDENCIES.md)

## Installation

Refer to [INSTALL.md](INSTALL.md)

## Usage

	python -m teos_cli [global options] command [command options] [arguments]
	
#### Global options

- `--rpcconnect`:	API server where to send the requests. Defaults to 'localhost' (modifiable in conf file).
- `--rpcport` :	API port where to send the requests. Defaults to '9814' (modifiable in conf file).
- `-h --help`: 	shows a list of commands or help for a specific command.

#### Commands

The command line interface has, currently, two commands:

- `get_all_appointments`: returns a list of all the appointments currently in the watchtower.
- `help`: shows a list of commands or help for a specific command.
	
	
### get_all_appointments

This command is used to get information about all the appointments stored in a Eye of Satoshi tower.

**Responses**

This command returns all appointments stored in the watchtower. More precisely, it returns all the "response_trackers" and "watchtower_appointments" in a dictionary. 

#### Usage

        python -m teos_cli get_all_appointments

### help

Shows the list of commands or help about how to run a specific command.

#### Usage
	python -m teos_cli help
	
or

	python -m teos_cli help command
