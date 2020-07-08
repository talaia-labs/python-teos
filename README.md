## State of the Code

Currently working on updating the software to match [BOLT13 rev1](https://github.com/sr-gi/bolt13).

# The Eye of Satoshi (TEOS)

The Eye of Satoshi is a Lightning watchtower compliant with [BOLT13](https://github.com/sr-gi/bolt13), written in Python 3.

`teos` consists in four main modules:

- `teos`: including the tower's main functionality (server-side)
- `cli`: including a reference command line interface (client-side)
- `common`: including shared functionality between `teos` and `cli`.
- `watchtower-plugin`: including a watchtower client plugin for c-lightning.

Additionally, tests for every module can be found at `tests`.

## Dependencies
Refer to [DEPENDENCIES.md](DEPENDENCIES.md)

## Installation

Refer to [INSTALL.md](INSTALL.md)

## Running TEOS

Make sure bitcoind is running before running TEOS (it will fail at startup if it cannot connect to bitcoind). You can find
[here](DEPENDENCIES.md#installing-bitcoind) a sample config file.

Before you can run TEOS, you need to follow a few more configuration steps.

### Configuration file and command line parameters

`teos` comes with a default configuration that can be found at [teos/\_\_init\_\_.py](teos/__init__.py). 

The configuration includes, amongst others, where your data folder is placed, what network it connects to, etc.

To change the configuration defaults you can:

- Define a configuration file named `teos.conf` following the template (check [teos/template.conf](teos/template.conf)) and place it in the `data_dir` (that defaults to `~/.teos/`)

and / or 

- Add some global options when running the daemon (run `teosd.py -h` for more info).

### Tower id and signing key

`teos` needs a pair of keys that will serve as tower id and signing key. The former can be used by users to identify the tower, whereas the latter is used by the tower to sign responses. You can follow [generate keys](#generate-keys) to generate them.

### Starting the TEOS daemon 👁

Now that everything is ready, you can run `teos` by running `teosd.py` under `teos`:

```
python -m teos.teosd
```

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
A `teos` image can be built from the Dockerfile located in `/docker`. You can create the image by running:

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

## Interacting with a TEOS Instance

You can interact with a `teos` instance (either run by yourself or someone else) by using `teos_cli` under `cli`.

Since `teos_cli` works independently of `teos`, it uses a different configuration. The defaults can be found at [cli/\_\_init\_\_.py](cli/__init__.py). The same approach as with `teosd` is followed:

- A config file (`~/.teos_cli/teos_cli.conf`) can be set to change the defaults.
- Some options ca also be changed via command line. 
- The configuration file template can be found at [cli/template.conf](cli/template.conf))

`teos_cli` needs an independent set of keys and, top of that, a copy of tower's the public key (`teos_pk.der`). Check [generate keys](#generate-keys) for more on how to set this.

Notice that `teos_cli` is a simple way to interact with `teos`, but ideally that should be part of your wallet functionality (therefore why they are independent entities). `teos_cli` can be used as an example for how to send data to a [BOLT13](https://github.com/sr-gi/bolt13) compliant watchtower.

## Generate Keys

In order to generate a pair of keys for `teos` (or `teos_cli`) you can use `generate_keys.py`. 

The script generates and stores a set of keys on disk (by default it outputs them in the current directory and names them `teos_sk.der` and `teos_pk.der`). The name and output directory can be changed using `-n` and `-d` respectively.

The following command will generate a set of keys for `teos` and store it in the default data directory (`~/.teos`):
```
python generate_keys.py -d ~/.teos
``` 

The following command will generate a set of keys for `teos_cli` and store it in the default data directory (`~/.teos_cli`):
```
python generate_keys.py -n cli -d ~/.teos_cli
``` 

Notice that `cli` needs a copy of the tower public key, so you should make a copy of that if you're using different data directories (as in this example):

```
cp ~/.teos/teos_pk.der ~/.teos_cli/teos_pk.der 
```

## Contributing 
Refer to [CONTRIBUTING.md](CONTRIBUTING.md)
