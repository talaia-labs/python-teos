# Install 

`wt_cli` has some dependencies that can be satisfied by following [DEPENDENCIES.md](DEPENDENCIES.md). If your system already satisfies the dependencies, you can skip that part.

There are two ways of running `wt_cli`: adding the library to the `PYTHONPATH` env variable, or running it as a module

## Modifying `PYTHONPATH`
In order to run `wt_cli`, you should set your `PYTHONPATH` env variable to include the folder that contains the `apps` folder. You can do so by running:

	export PYTHONPATH=$PYTHONPATH:<absolute_path_to_apps>
	
For example, for user alice running a UNIX system and having `apps` in her home folder, she would run:
	
	export PYTHONPATH=$PYTHONPATH:/home/alice/
	
You should also include the command in your `.bash_rc` to avoid having to run it every time you open a new terminal. You can do it by running:

	echo 'export PYTHONPATH=$PYTHONPATH:<absolute_path_to_apps>' >> ~/.bash_rc
	
Once the `PYTHONPATH` is set, you should be able to run `wt_cli` straightaway. Try it by running:

	cd <absolute_path_to_apps>/apps/cli
	python wt_cli.py -h
	
## Running `wt_cli` as a module
Python code can be also run as a module, to do you need to use `python -m`. From `apps` **parent** directory run:

    python -m apps.cli.wt_cli -h
    
Notice that if you run `wt_cli` as a module, you'll need to replace all the calls to `python wt_cli.py <argument>` to `python -m apps.cli.wt_cli <argument>` 