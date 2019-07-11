# pisa-cli

`pisa-cli` is a command line interface to interact with the PISA server, written in Python3.

## Dependencies
Refer to [DEPENDENCIES.md](DEPENDENCIES.md)

## Installation

Refer to [INSTALL.md](INSTALL.md)

## Usage

	python pisa-cli.py [global options] command [command options] [arguments]
	
### Global options

- `-s, --server`:	API server where to send the requests. Defaults to btc.pisa.watch (modifiable in \_\_init\_\_.py)
- `-p, --port` :	API port where to send the requests. Defaults to 9814 (modifiable in \_\_init\_\_.py)
- `-d, --debug`: 	shows debug information and stores it in pisa.log
- `-h --help`: 	shows a list of commands or help for a specific command.

### Commands

The command line interface has, currently, three commands:

- `add_appointment`: registers a json formatted appointment to the PISA server.
- `get_appointment`: gets json formatted data about an appointment from the PISA server.
- `help`: shows a list of commands or help for a specific command.

## add_appointment

This command is used to register appointments to the PISA server. Appointments **must** be `json` encoded, and match the following format:

	{ "tx": tx,
	  "tx_id": tx_id,
	  "start_time": s,
	  "end_time": e,
	  "dispute_delta": d
	}
	
`tx` **must** be the raw justice transaction that will be encrypted before sent to the PISA server. `type(tx) = hex encoded str`

`tx_id` **must** match the **commitment transaction id**, and will be used to encrypt the **justice transaction** and **generate the locator**. `type(tx_id) = hex encoded str`

`s` is the time when the PISA server will start watching your transaction, and will normally match to whenever you will be offline. `s` is measured in block height, and must be **higher than the current block height** and not too close to it. `type(s) = int`

`e` is the time where the PISA server will stop watching your transaction, and will normally match which whenever you should be back online. `e` is also measured in block height, and must be **higher than** `s`. `type(e) = int`

`d` is the time PISA would have to respond with the **justice transaction** once the **dispute transaction** is seen in the blockchain. `d` must match with the `OP_CSV` specified in the dispute transaction. If the dispute_delta does not match the `OP_CSV `, PISA would try to respond with the justice transaction anyway, but success is not guaranteed. `d` is measured in blocks and should be at least `20`. `type(d) = int`

The API will return a `text/plain` HTTP response code `200/OK` if the appointment is accepted, with the locator encoded in the response text, or a `400/Bad Request` if the appointment is rejected, with the rejection reason encoded in the response text. 


### Usage

	python pisa-cli add_appointment [command options] <appointment>/<path_to_appointment_file>
	
if `-f, --file` **is** specified, then the command expects a path to a json file instead of a json encoded
	string as parameter.
	
### Options
- `-f, --file path_to_json_file`	 loads the appointment data from the specified json file instead of command line.

**Appointment can be in three states**

- `not_found`: meaning the locator is not recognised by the API. This could either mean the locator is wrong, or the appointment has already been fulfilled (the PISA server does not have any kind of data persistency for now).
- `being_watched`: the appointment has been accepted by the PISA server and it's being watched at the moment. This stage means that the dispute transaction has now been seen yet, and therefore no justice transaction has been published.
- `dispute_responded`: the dispute was found by the watcher and the corresponding justice transaction has been broadcast by the node. In this stage PISA is actively monitoring until the justice transaction reaches enough confirmations and making sure no fork occurs in the meantime.

**Response formats**

**not_found**

	[{"locator": appointment_locator, 
	"status":"not_found"}]
	
**being_watched**

	[{"cipher": "AES-GCM-128",
	"dispute_delta": d,
	"encrypted_blob": eb,
	"end_time": e,
	"hash_function":  "SHA256",
	"locator": appointment_locator,
	"start_time": s,
	"status": "being_watched"}]
	
**dispute_responded**

	[{"locator": appointment_locator,
	"justice_rawtx": j,
	"appointment_end": e,
	"status": "dispute_responded"
	"confirmations": c}]
	
### Usage

	python pisa-cli get_appointment <appointment_locator>
	

	
## help

Shows the list of commands or help about how to run a specific command.

### Usage
	python pisa-cli help
	
or

	python pisa-cli help command

## Example

1. Generate a new dummy appointment. **Note:** this appointment will never be fulfilled (it will eventually expire) since it does not corresopond to a valid transaction. However it can be used to interact with the PISA API.

    ```
    python pisa-cli.py generate_dummy_appointment
    ```

    That will create a json file that follows the appointment data structure filled with dummy data and store it in   `dummy_appointment_data.json`.

2. Send the appointment to the PISA API. Which will then start monitoring for matching transactions.

    ```
    python pisa-cli.py add_appointment -f dummy_appointment_data.json
    ```

    This returns a appointment locator that can be used to get updates about this appointment from the PISA.

3. Test that PISA is still watching the appointment by replacing the appointment locator received into the following command:

    ```
    python pisa-cli.py get_appointment <appointment_locator>
    ```

## PISA API	

If you wish to read about the underlying API, and how to write your own tool to interact with it, refer to [PISA-API.md](PISA-API.md)