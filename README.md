## State of the Code

Currently working on updating the software to match [BOLT13 rev1](https://github.com/sr-gi/bolt13).

# The Eye of Satoshi (TEOS)

The Eye of Satoshi is a Lightning watchtower compliant with [BOLT13](https://github.com/sr-gi/bolt13), written in Python 3.

`teos` consists in four main modules:

- `teos`: including the tower's main functionality (server-side).
- `cli`: including a reference command line interface.
- `common`: including shared functionality between server and client side (useful to build a client).
- `watchtower-plugin`: including a watchtower client plugin for c-lightning.

Additionally `contrib` contains tools that are external to the tower (currently `teos_client`, an example Python client for the tower). 

Tests for every module can be found at `tests`.

## Dependencies
Refer to [DEPENDENCIES.md](DEPENDENCIES.md)

## Installation

Refer to [INSTALL.md](INSTALL.md)

## Running TEOS

Make sure bitcoind is running before running TEOS (it will fail at startup if it cannot connect to bitcoind). You can find
[here](DEPENDENCIES.md#installing-bitcoind) a sample config file.

### Starting the TEOS daemon 👁

You can run `teos` by running `teosd.py` under `teos`:

```
python -m teos.teosd
```

### Configuration file and command line parameters

`teos` comes with a default configuration that can be found at [teos/\_\_init\_\_.py](teos/__init__.py). 

The configuration includes, amongst others, where your data folder is placed, what network it connects to, etc.

To change the configuration defaults you can:

- Define a configuration file named `teos.conf` following the template (check [teos/template.conf](teos/template.conf)) and place it in the `data_dir` (that defaults to `~/.teos/`)

and / or 

- Add some global options when running the daemon (run `teosd.py -h` for more info).

### Passing command line options to `teosd`

Some configuration options can also be passed as options when running `teosd`. We can, for instance, pick the network as follows:

```
python -m teos.teosd --btcnetwork=regtest
```

### Running TEOS in another network

By default, `teos` runs on `mainnet`. In order to run it on another network you need to change the network parameter in the configuration file or pass the network parameter as a command line option. Notice that if teos does not find a `bitcoind` node running in the same network that it is set to run, it will refuse to run.

The configuration file option to change the network where `teos` will run is `btc_network` under the `bitcoind` section:

```
[bitcoind]
btc_rpc_user = user
btc_rpc_password = passwd
btc_rpc_connect = localhost
btc_network = mainnet
```

For regtest, it should look like:

```
[bitcoind]
btc_rpc_user = user
btc_rpc_password = passwd
btc_rpc_connect = localhost
btc_network = regtest
```

## Running `teos` in a docker container
A `teos` image can be built from the Dockerfile located in `docker`. You can create the image by running:

	cd python-teos
	docker build -f docker/Dockerfile -t teos .
	
Then you can create a container by running:

	docker run -it -e ENVS teos
	
Notice that ENV variables are optional, if unset the corresponding default setting is used. The following ENVs are available:

```
- API_BIND=<teos_api_hostname>
- API_PORT=<teos_api_port>
- BTC_NETWORK=<btc_network>
- BTC_RPC_CONNECT=<btc_node_hostname>
- BTC_RPC_PORT=<btc_node_port>
- BTC_RPC_USER=<btc_rpc_username>
- BTC_RPC_PASSWORD=<btc_rpc_password>
- BTC_FEED_CONNECT=<btc_zmq_hostname>
- BTC_FEED_PORT=<btc_zmq_port>
```

You may also want to run docker with a volume, so you can have data persistence in `teos` databases and keys.
If so, run:

    docker volume create teos-data
    
And add the the mount parameter to `docker run`:

    --mount source=teos-data,target=/root/.teos

If you are running `teos` and `bitcoind` in the same machine, continue reading for how to create the container based on your OS.

### `bitcoind` running on the same machine (UNIX)
The easiest way to run both together in he same machine using UNIX is to set the container to use the host network.
	
For example, if both `teos` and `bitcoind` are running on default settings, run
    
```
docker run --network=host \
  --name teos \
  --mount source=teos-data,target=/root/.teos \
  -e BTC_RPC_USER=<rpc username> \
  -e BTC_RPC_PASSWD=<rpc password> \
  -it teos
```

Notice that you may still need to set your RPC authentication details, since, hopefully, your credentials won't match the `teos` defaults.

### `bitcoind` running on the same machine (OSX or Windows)

Docker for OSX and Windows does not allow to use the host network (nor to use the `docker0` bridge interface). To workaround this
you can use the special `host.docker.internal` domain.

```
docker run -p 9814:9814 \
  --name teos \
  --mount source=teos-data,target=/root/.teos \
  -e BTC_RPC_CONNECT=host.docker.internal \
  -e BTC_FEED_CONNECT=host.docker.internal \
  -e BTC_RPC_USER=<rpc username> \
  -e BTC_RPC_PASSWD=<rpc password> \
  -e API_BIND=0.0.0.0 \
  -it teos
```

Notice that we also needed to add `API_BIND=0.0.0.0` to bind the API to all interfaces of the container.
Otherwise it will bind to `localost` and we won't be able to send requests to the tower from the host.

### Tower id and signing key

`teos` needs a pair of keys that will serve as tower id and signing key. The former can be used by users to identify the tower, whereas the latter is used by the tower to sign responses. These keys are automatically generated on the first run, and can be refreshed by running `teos` with the `--overwritekey` flag.


## Interacting with a TEOS Instance

You can interact with a `teos` instance (either run by yourself or someone else) by using `teos_cli` under `teos/cli`. This is an admin tool that has privileged access to the watchtower, and it should therefore only be used within a trusted environment (for example, the same machine).

While `teos_cli` works independently of `teos`, it shares the same configuration file by default, of which it only uses a subset of its settings. The folder can be changed using the `--datadir` command line argument, if desired.

For help on the available arguments and commands, you can run:

```
python -m teos.cli.teos_cli -h
```

## Interacting with TEOS as a client

The [contrib/client](contrib/client) folder contains an example Python client that can interact with the watchtower in order to register, add appointments and later retrieve them.

See [here](contrib/client) for more information on how to use the client.

Note that while the client is a simple way to interact with `teos`, ideally its functionality should be part of your wallet or lightning node. `teos_client` can be used as an example for how to send data to a [BOLT13](https://github.com/sr-gi/bolt13) compliant watchtower.

## Contributing 
Refer to [CONTRIBUTING.md](CONTRIBUTING.md)
