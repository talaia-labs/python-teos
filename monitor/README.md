This is a system monitor for viewing available user slots, appointments, and other data related to Teos. Data is loaded and searched using Elasticsearch and visualized using Kibana to produce something like this:

![Dashboard example](https://ibb.co/ypBtfdM)

### Prerequisites

Need to already be running a bitcoin node and a Teos watchtower. (See: https://github.com/talaia-labs/python-teos)

### Installation

Install and run both Elasticsearch and Kibana, which both need to be running for this visualization tool to work. 

https://www.elastic.co/guide/en/elasticsearch/reference/current/install-elasticsearch.html
https://www.elastic.co/guide/en/kibana/current/install.html

### Dependencies

Install the dependencies by running:

```pip install -r requirements.txt```

### Config 

It is also required to create a config file in this directory. `sample-monitor.conf` in this directory provides an example.

Create a file named `monitor.conf` in this directory with the correct configuration values, including the correct host and port where Elasticsearch and Kibana are running, either on localhost or on another host.

### Run it

Follow the same instructions as shown here for running the module: https://github.com/talaia-labs/python-teos/blob/master/INSTALL.md

In short, run it with:

```python3 -m monitor.monitor_start```
