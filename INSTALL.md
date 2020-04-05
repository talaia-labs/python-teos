# Install 

`teos` has some dependencies that can be satisfied by following [DEPENDENCIES.md](DEPENDENCIES.md). If your system already satisfies the dependencies, you can skip that part.

There are two ways of running `teos`: running it as a module or adding the library to the `PYTHONPATH` env variable.

## Running `teos` as a docker container
`teos` container can be build from Dockerfile attached to the repo. ENV variables are optional, if not set defaults are used.

	git clone https://github.com/talaia-labs/python-teos
	cd python-teos
	docker build . -t teos
    docker run -it -e BTC_RPC_USER=<rpc username> -e BTC_RPC_PASSWD=<rpc password> -e BTC_RPC_HOST=<hostname> -e BTC_RPC_PORT=<port> teos

## Running `teos` as a Module
The **easiest** way to run `teos` is as a module. To do so you need to use `python -m`. From the teos parent directory run:

    python -m teos.teosd -h
    
Notice that if you run `teos` as a module, you'll need to replace all the calls from `python teosd.py` to `python -m teos.teosd` 

## Modifying `PYTHONPATH`
**Alternatively**, you can add `teos` to your `PYTHONPATH` by running:

	export PYTHONPATH=$PYTHONPATH:<absolute_path_to_teos_parent>
	
For example, for user alice running a UNIX system and having `python-teos` in her home folder, she would run:
	
	export PYTHONPATH=$PYTHONPATH:/home/alice/python-teos/
	
You should also include the command in your `.bashrc` to avoid having to run it every time you open a new terminal. You can do it by running:

	echo 'export PYTHONPATH=$PYTHONPATH:<absolute_path_to_teos_parent>' >> ~/.bashrc
	
Once the `PYTHONPATH` is set, you should be able to run `teos` straightaway. Try it by running:

	cd <absolute_path_to_cli_parent>/teos
	python teosd.py -h
	
## Modify Configuration Parameters
If you'd like to modify some of the configuration defaults (such as the bitcoind rpcuser and password) you can do so in the config file located at:

	 <data_dir>/.teos/teos.conf
	 
`<data_dir>` defaults to your home directory (`~`).
