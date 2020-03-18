# Dependencies

`teos` has both system-wide and Python dependencies. This document walks you through how to satisfy them.

## System-wide Dependencies

`teos` has the following system-wide dependencies:

- `python3`
- `pip3`
- `bitcoind`

### Checking if the dependencies are already satisfied

Most UNIX systems ship with `python3` already installed, whereas OSX systems tend to ship with `python2`. In order to check our python version we should run:

	python --version

For what we will get something like:

	Python 2.X.X
	
Or
	
	Python 3.X.X
	
It is also likely that, if `python3` is installed in our system, the `python` alias is not set to it but instead to `python2`. In order to check so, we can run:

	python3 --version

If `python3` is installed but the `python` alias is not set to it, we should either set it, or use `python3` to run `teos`.

Regarding `pip`, we can check what version is installed in our system (if any) by running:

	pip --version

For what we will get something like:

	pip X.X.X from /usr/local/lib/python2.X/dist-packages/pip (python 2.X)
	
Or

	pip X.X.X from /usr/local/lib/python3.X/dist-packages/pip (python 3.X)

A similar thing to the `python` alias applies to the `pip` alias. We can check if pip3 is install by running:

	pip3 --version
	
And, if it happens to be installed, change the alias to `pip3`, or use `pip3` instead of `pip`.

### Installing bitcoind

`teos` runs on top of a Bitcoin Core node. Other underlaying Bitcoin nodes are not supported at the moment. 

You can get Bitcoin Core from [bitcoin.org](https://bitcoin.org/en/download).

Bitcoin needs to be running with the following options enables:

- `zmq` for rawblockhash notifications
- `txindex` to be able to look for non-wallet transactions
- `server` to run rpc commands

Here's an example of a `bitcoin.conf` you can use:

```
# [debug]
regtest=1
daemon=1
debug=1
logips=1

# [rpc]
server=1
rpcuser=user
rpcpassword=passwd

# [blockchain]
txindex=1

# [ZMQ]
zmqpubhashblock=tcp://127.0.0.1:28332
zmqpubrawblock=tcp://127.0.0.1:28332
zmqpubhashtx=tcp://127.0.0.1:28333
zmqpubrawtx=tcp://127.0.0.1:28333
```

### Installing the Dependencies

`python3` ca be downloaded from the [Python official website](https://www.python.org/downloads/) or installed using a package manager, depending on your distribution. Examples for both UNIX-like and OSX systems are provided.

#### Ubuntu

`python3` can be installed using `apt` as follows:

	sudo apt-get update
	sudo apt-get install python3
	
and for `pip3`:

	sudo apt-get install python3-pip
	pip install --upgrade pip==9.0.3
	
#### OSX

`python3` can be installed using `Homebrew` as follows:
	
	brew install python3

`pip3` will be installed alongside `python3` in this case.

## Python Dependencies

`teos` has the following dependencies (which can be satisfied by using `pip install -r requirements.txt`):

- `zmq`
- `flask`
- `cryptography`
- `coincurve`
- `pyzbase32`
- `requests`
- `plyvel`

