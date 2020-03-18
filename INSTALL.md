# Install 

`teos` has some dependencies that can be satisfied by following [DEPENDENCIES.md](DEPENDENCIES.md). If your system already satisfies the dependencies, you can skip that part.

There are two ways of running `teos`: adding the library to the `PYTHONPATH` env variable, or running it as a module.

## Modifying `PYTHONPATH`
In order to run `teos`, you should set your `PYTHONPATH` env variable to include the teos parent folder. You can do so by running:

	export PYTHONPATH=$PYTHONPATH:<absolute_path_to_teos_parent>
	
For example, for user alice running a UNIX system and having `teos` in her home folder, she would run:
	
	export PYTHONPATH=$PYTHONPATH:/home/alice/
	
You should also include the command in your `.bashrc` to avoid having to run it every time you open a new terminal. You can do it by running:

	echo 'export PYTHONPATH=$PYTHONPATH:<absolute_path_to_teos_parent>' >> ~/.bashrc
	
Once the `PYTHONPATH` is set, you should be able to run `teos` straightaway. Try it by running:

	cd <absolute_path_to_teos_parent>/teos/
	python teosd.py
	
## Running `teos` as a module
Python code can be also run as a module, to do so you need to use `python -m`. From the teos parent directory run:

    python -m teos.teosd
    
Notice that if you run `teos` as a module, you'll need to replace all the calls from `python teosd.py` to `python -m teos.teosd` 

## Modify configuration parameters
If you'd like to modify some of the configuration defaults (such as the user directory, where the logs will be stored) you can do so in the config file located at:

	 <absolute_path_to_teos_parent>/teos/conf.py
