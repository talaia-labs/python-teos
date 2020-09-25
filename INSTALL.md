# Install 

`teos` has some dependencies that can be satisfied by following [DEPENDENCIES.md](DEPENDENCIES.md). If your system already satisfies the dependencies, you can skip that part.

There are two ways of running `teos`: running it as a module or adding the library to the `PYTHONPATH` env variable.

    python setup.py install

Once this command is completed, the executables for `teosd` and `teos_cli` will be available in the shell.
	
## Modify Configuration Parameters
If you'd like to modify some of the configuration defaults (such as the bitcoind rpcuser and password) you can do so in the config file located at:

	 <data_dir>/.teos/teos.conf
	 
`<data_dir>` defaults to your home directory (`~`).
