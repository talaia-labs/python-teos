# Install 

`pisa-cli` has some dependencies that can be satisfied by following [DEPENDENCIES.md](DEPENDENCIES.md). If your system already satisfies the dependencies, you can skip that part.

In order to run `pisa-cli`, you should set your `PYTHONPATH` env variable to include the folder that contains the `apps` folder. You can do so by running:

	export PYTHONPATH=$PYTHONPATH:<absolute_path_to_apps>
	
For example, for user alice running a UNIX system and having `apps` in her home folder, she would run:
	
	export PYTHONPATH=$PYTHONPATH:/home/alice/
	
You should also include the command in your `.bash_rc` to avoid having to run it every time you open a new terminal. You can do it by running:

	echo 'export PYTHONPATH=$PYTHONPATH:<absolute_path_to_apps>' >> ~/.bash_rc


Create the tower configuration file called `conf.py` in `/pisa_btc/pisa` directory. `Sample_conf.py` shows what values can be set in the file, including suggested default values. 
	
Once that's all set, you should be able to run `pisa-cli` straightaway. Try it by running:

	cd <absolute_path_to_apps>/apps/cli
	python pisa-cli.py -h
