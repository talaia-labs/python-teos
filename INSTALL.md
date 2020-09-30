# Install 

`teos` has some dependencies that can be satisfied by following [DEPENDENCIES.md](DEPENDENCIES.md). If your system already satisfies the dependencies, you can skip that part.

There are two ways of installing `teos`, from source or getting it from PyPi (the Python Package Index).

No matter the way you chose, once installed the executables for `teosd` and `teos-cli` will be available in the shell.

## Installing from source

`teos` can be installed from source by running (from  `python-teos/`):

```
pip install .
```

## Installing via PyPi

`teos` can be installed from PyPi bu running:

```
pip install python-teos
```

	
## Modify Configuration Parameters
If you'd like to modify some of the configuration defaults (such as the bitcoind rpcuser and password) you can do so in the config file located at:

	 <data_dir>/.teos/teos.conf
	 
`<data_dir>` defaults to your home directory (`~`).
