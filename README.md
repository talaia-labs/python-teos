## State of the code

Currently working on updating the software to match [BOLT13 rev1](https://github.com/sr-gi/bolt13).

# The Eye of Satoshi (TEOS)

The Eye of Satoshi is a Lightning watchtower compliant with [BOLT13](https://github.com/sr-gi/bolt13), written in Python 3.

TEOS consists in three main modules:

- `teos`: including the tower's main functionality (server-side)
- `cli`: including a reference command line interface (client-side)
- `common`: including shared functionality between `teos` and `cli`.

Additionally, tests for every module can be found at `tests`.

### Running TEOS
In order to run `teos` you will need to create a configuration file (follow [INSTALL.md](INSTALL.md)) and run `teosd.py`. Currently you will also need a set of keys (to sign appointments) stored in your data directory.

You can use `generate_keys.py` to generate those keys.

### Interacting with a TEOS instance
You can interact with a `teos` instance (either run by yourself or someone else) by using `teos_cli` under `cli`.

Since `teos_cli` works independently of `teos`, you will need a separate configuration file for this (follow [cli/INSTALL.md](cli/INSTALL.md)).

`teos_cli` will also need an independent set of keys (that can be generated using `generate_keys.py`) as well as the public key of the tower instance (`teos_pk.der`). The same data directory can be used for both if you are running things locally.

Notice that `teos_cli` is a simple way to interact with `teos`, but ideally that should be part of your wallet functionality (therefore why they are independent entities). `teos_cli` can be used as an example for how to send data to a [BOLT13](https://github.com/sr-gi/bolt13) compliant watchtower.
 
## Dependencies
Refer to [DEPENDENCIES.md](DEPENDENCIES.md)

## Installation

Refer to [INSTALL.md](INSTALL.md)

## Contributing 
Refer to [CONTRIBUTING.md](CONTRIBUTING.md)