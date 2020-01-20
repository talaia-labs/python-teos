# Copy this file with your own configuration and save it as conf.py

# Docker
DOCK_NETWORK_NAME = "pisa_net"
DOCK_NETWORK_SUBNET = "172.16.0.0/16"
DOCK_NETWORK_GW = "172.16.0.1"
DOCK_CONTAINER_NAME_PREFIX = "btc_n"
DOCK_IMAGE_NAME = "sandbox_btc"
DOCKER_INI_PORT_MAPPING = 22000
DOCKER_RPC_PORT_MAPPING = 18444
DOCKER_ZMQ_BLOCK_PORT_MAPPING = 28334

# Log
LOG_FILE = "bitcoin_sandbox.log"

# Graphs
BITCOIN_GRAPH_FILE = "./graphs/basic3.graphml"
LN_GRAPH_FILE = "./graphs/basic3_ln.graphml"
DEFAULT_LN_GRAPH_WEIGHT = 10000
