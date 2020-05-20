# teos_cli

`teos_cli` is a command line interface to interact with the Eye of Satoshi watchtower server, written in Python3.

## Dependencies
Refer to [DEPENDENCIES.md](DEPENDENCIES.md)

## Installation

Refer to [INSTALL.md](INSTALL.md)

## Usage

	python teos_cli.py [global options] command [command options] [arguments]
	
#### Global options

- `--apiconnect`:	API server where to send the requests. Defaults to 'localhost' (modifiable in conf file).
- `--apiport` :	API port where to send the requests. Defaults to '9814' (modifiable in conf file).
- `-h --help`: 	shows a list of commands or help for a specific command.

#### Commands

The command line interface has, currently, four commands:

- `register`: registers your user with the tower.
- `add_appointment`: sends a json formatted appointment to the tower.
- `get_appointment`: gets json formatted data about an appointment from the tower.
- `help`: shows a list of commands or help for a specific command.

### register
This commands serves as registration. It sends your public key to the tower to create a subscription (fee atm) and returns a number of available appointment slots in the tower. Toping up the subscription can be done by simply sending a register message again.

Notice that you need to be register before sending any other type of request to the tower.

#### Usage

	python teos_cli.py register
	
	
### add_appointment

This command is used to send appointments to the watchtower. Appointments **must** be `json` encoded, and match the following format:

	{ "tx": tx,
	  "tx_id": tx_id,
	  "to_self_delay": d }
	
`tx` **must** be the raw penalty transaction that will be encrypted before sent to the watchtower. `type(tx) = hex encoded str`

`tx_id` **must** match the **commitment transaction id**, and will be used to encrypt the **penalty transaction** and **generate the locator**. `type(tx_id) = hex encoded str`

`s` is the time when the watchtower will start watching your transaction, and will normally match to whenever you will be offline. `s` is measured in block height, and must be **higher than the current block height**. `type(s) = int`

`e` is the time where the watchtower will stop watching your transaction, and will normally match with whenever you should be back online. `e` is also measured in block height, and must be **higher than** `s`. `type(e) = int`

`d` is the time the watchtower would have to respond with the **penalty transaction** once the **dispute transaction** is seen in the blockchain. `d` must match with the `OP_CSV` specified in the dispute transaction. If the to\_self\_delay does not match the `OP_CSV`, the watchtower will try to respond with the penalty transaction anyway, but success is not guaranteed. `d` is measured in blocks and should be at least `20`. `type(d) = int`

The API will return a `application/json` HTTP response code `200/OK` if the appointment is accepted, with the locator encoded in the response text, or a `400/Bad Request` if the appointment is rejected, with the rejection reason encoded in the response text. 


#### Usage

	python teos_cli.py add_appointment [command options] <appointment>/<path_to_appointment_file>
	
if `-f, --file` **is** specified, then the command expects a path to a json file instead of a json encoded string as parameter.
	
#### Options
- `-f, --file path_to_json_file`	 loads the appointment data from the specified json file instead of command line.

### get_appointment	

 This command is used to get information about a specific appointment from the Eye of Satoshi.	

**Appointment can be in three states:**

- `not_found`: meaning the locator is not recognised by the tower. This can either mean the locator is wrong, or the appointment has already been fulfilled (the tower does not keep track of completed appointments for now).
- `being_watched`: the appointment has been accepted by the tower and it's being watched at the moment. This stage means that the dispute transaction has not been seen yet, and therefore no penalty transaction has been broadcast.
- `dispute_responded`: the dispute was found by the watcher and the corresponding penalty transaction has been broadcast by the node. In this stage the tower is actively monitoring until the penalty transaction reaches enough confirmations and making sure no fork occurs in the meantime.

**Response formats**

**not_found**

	{
		"locator": l,
		"status": "not_found"
	}
	
**being_watched**

	{
		"locator": l,
		"status": "being_watched",
		"appointment":
			{
				"encrypted_blob": eb,
				"locator": appointment_locator,
				"status": "being_watched",
				"to_self_delay": d
			}
	}
	
**dispute_responded**

	{
		"locator": l,
		"status": "dispute_responded",
		"appointment":
			{
				"dispute_txid": dispute_txid,
				"locator": appointment_locator,
				"penalty_rawtx": penalty_rawtx,
				"penalty_txid": penalty_txid,
				"status": "dispute_responded"
			}
	}
	
#### Usage

	python teos_cli.py get_appointment <appointment_locator>
	
### get_all_appointments

This command is used to get information about all the appointments stored in a Eye of Satoshi tower.

**Responses**

This command returns all appointments stored in the watchtower. More precisely, it returns all the "response_trackers" and "watchtower_appointments" in a dictionary. 

#### Usage

        python teos_cli.py get_all_appointments

### help

Shows the list of commands or help about how to run a specific command.

#### Usage
	python teos_cli.py help
	
or

	python teos_cli.py help command

## Example
1. Register with the tower.

```
python teos_cli.py register
```

2. Generate a new dummy appointment. **Note:** this appointment will never be fulfilled (it will eventually expire) since it does not correspond to a valid transaction. However it can be used to interact with the Eye of Satoshi's API.

    ```
	echo '{"tx": "4615a58815475ab8145b6bb90b1268a0dbb02e344ddd483f45052bec1f15b1951c1ee7f070a0993da395a5ee92ea3a1c184b5ffdb2507164bf1f8c1364155d48bdbc882eee0868ca69864a807f213f538990ad16f56d7dfb28a18e69e3f31ae9adad229e3244073b7d643b4597ec88bf247b9f73f301b0f25ae8207b02b7709c271da98af19f1db276ac48ba64f099644af1ae2c90edb7def5e8589a1bb17cc72ac42ecf07dd29cff91823938fd0d772c2c92b7ab050f8837efd46197c9b2b3f", "tx_id": "0b9510d92a50c1d67c6f7fc5d47908d96b3eccdea093d89bcbaf05bcfebdd951", "to_self_delay": 20}' > dummy_appointment_data.json
    ```

    That will create a json file that follows the appointment data structure filled with dummy data and store it in `dummy_appointment_data.json`.

3. Send the appointment to the tower API. Which will then start monitoring for matching transactions.

    ```
    python teos_cli.py add_appointment -f dummy_appointment_data.json
    ```

    This returns an appointment locator that can be used to get updates about this appointment from the tower.

4. Test that the tower is still watching the appointment by replacing the appointment locator received into the following command:

    ```
    python teos_cli.py get_appointment <appointment_locator>
    ```

## Try our live instance

By default, `teos_cli` will connect to your local instance (running on localhost). There are also a couple of live instances running, one for mainet and one for testnet:

- testnet endpoint = `teos-testnet.pisa.watch:443`
- mainnet endpoint = `teos.pisa.watch:443` or `theeyeofsatoshi.pisa.watch:443`

### Connecting to the mainnet instance
Add `--apiconnect  --apiport 443` to your calls, for example:

```
python teos_cli.py --apiconnect=https://teos.pisa.watch add_appointment --apiport=443 -f dummy_appointment_data.json 
```

You can also change the config file to avoid specifying the server every time:
```
api_connect = https://teos.pisa.watch
api_port = 443
```
