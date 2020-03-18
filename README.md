## State of the Code

Currently working on updating the software to match [BOLT13 rev1](https://github.com/sr-gi/bolt13).

# The Eye of Satoshi (TEOS)

The Eye of Satoshi is a Lightning watchtower compliant with [BOLT13](https://github.com/sr-gi/bolt13), written in Python 3.

`teos` consists in three main modules:

- `teos`: including the tower's main functionality (server-side)
- `cli`: including a reference command line interface (client-side)
- `common`: including shared functionality between `teos` and `cli`.

Additionally, tests for every module can be found at `tests`.

By default, `teos` will run on `regtest`. In order to run it on another network you need to change your `bitcoin.conf` (to run in the proper network) and your `conf.py` to match the network name and rpc port:

```
BTC_RPC_PORT = 18443
BTC_NETWORK = "regtest"
```

### Running TEOS
You can run `teos` buy running `teosd.py` under `teos`. 

`teos` comes with a default configuration file (check [conf.py](teos/conf.py)). The configuration file include, amongst others, where your data folder is placed, what network it connects to, etc.

To run `teos` you need a set of keys (to sign appointments) stored in your data directory. You can follow [generate keys](#generate-keys) to generate them.

### Interacting with a TEOS Instance
You can interact with a `teos` instance (either run by yourself or someone else) by using `teos_cli` under `cli`.

Since `teos_cli` works independently of `teos`, it uses a different configuration file (check [cli/conf.py](cli/conf.py)).

`teos_cli` also needs an independent set of keys (that can be generated following [generate keys](#generate-keys)) as well as the public key of the tower instance (`teos_pk.der`). The same data directory can be used for both if you are running things locally.

Notice that `teos_cli` is a simple way to interact with `teos`, but ideally that should be part of your wallet functionality (therefore why they are independent entities). `teos_cli` can be used as an example for how to send data to a [BOLT13](https://github.com/sr-gi/bolt13) compliant watchtower.

### Generate Keys

In order to generate a pair of keys for `teos` (or `teos_cli`) you can use `generate_keys.py`. 

The script generates a set of keys (`teos_sk.der` and `teos_pk.der`) in the current directory, by default. The name and output directory can be changed using `-n` and `-d` respectively.

The following command will generate a set of keys for `teos` and store it in the default data directory (`~/.teos`):
```
python generate_keys.py -d ~./teos
``` 

The following command will generate a set of keys for `teos_cli` and store it in the default data directory (`~/.teos_cli`):
```
python generate_keys.py -n cli -d ~./teos_cli
``` 

Notice that `cli` needs a copy of the tower public key, so you should make a copy of that if you're using different data directories (as in this example):

```
cp ~./teos/teos_pk.der ~./teos_cli/teos_pk.der 
```

## Dependencies
Refer to [DEPENDENCIES.md](DEPENDENCIES.md)

## Installation

Refer to [INSTALL.md](INSTALL.md)

## Contributing 
Refer to [CONTRIBUTING.md](CONTRIBUTING.md)