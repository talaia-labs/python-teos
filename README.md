## State of the code

Currently working on updating the software to match [BOLT13 rev1](https://github.com/sr-gi/bolt13).

# The Eye of Satoshi (TEOS)

The Eye of Satoshi is a Lightning watchtower compliant with [BOLT13](https://github.com/sr-gi/bolt13), written in Python 3.

TEOS consists in three main modules:

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

To run `teos` you need a set of keys (to sign appointments) stored in your data directory. You can use `generate_keys.py` to generate those keys.

`teos` comes with a default configuration file (check [conf.py](teos/conf.py)). The configuration file include, amost others, where your data folder is placed, what network it connects to, etc.

### Interacting with a TEOS instance
You can interact with a `teos` instance (either run by yourself or someone else) by using `teos_cli` under `cli`.

Since `teos_cli` works independently of `teos`, it uses a different configuration file (check [cli/conf.py](cli/conf.py)).

`teos_cli` also needs an independent set of keys (that can be generated using `generate_keys.py`) as well as the public key of the tower instance (`teos_pk.der`). The same data directory can be used for both if you are running things locally.

Notice that `teos_cli` is a simple way to interact with `teos`, but ideally that should be part of your wallet functionality (therefore why they are independent entities). `teos_cli` can be used as an example for how to send data to a [BOLT13](https://github.com/sr-gi/bolt13) compliant watchtower.
 
## Dependencies
Refer to [DEPENDENCIES.md](DEPENDENCIES.md)

## Installation

Refer to [INSTALL.md](INSTALL.md)

## Contributing 
Refer to [CONTRIBUTING.md](CONTRIBUTING.md)