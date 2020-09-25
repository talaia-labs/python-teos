# Install 

`teos-client` has some dependencies that can be satisfied by following [DEPENDENCIES.md](DEPENDENCIES.md). If your system already satisfies the dependencies, you can skip that part.

Once the dependencies are satisfied, `teos-client` can be installed from source by running:

```
python setup.py install
```

`teos-client` will be available in the shell once the installation is completed.

## Modify configuration parameters
If you'd like to modify some of the configuration defaults (such as the user directory, where the logs and appointment receipts will be stored) you can do so in the config file located at:

	 <data_dir>/.teos_client/teos_client.conf
	 
`<data_dir>` defaults to your home directory (`~`).
