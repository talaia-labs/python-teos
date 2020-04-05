#!/bin/bash 

START_COMMAND="/usr/local/bin/python3 -m teos.teosd "

if [[ ! -z ${BTC_RPC_USER} ]]; then 
    START_COMMAND=$START_COMMAND" --btcrpcuser=""$BTC_RPC_USER"
fi

if [[ ! -z ${BTC_RPC_HOST} ]]; then 
    START_COMMAND=$START_COMMAND" --btcrpcconnect=""$BTC_RPC_HOST"
fi

if [[ ! -z ${BTC_RPC_PASSWD} ]]; then 
    START_COMMAND=$START_COMMAND" --btcrpcpassword=""$BTC_RPC_PASSWD"
fi

if [[ ! -z ${BTC_NETWORK} ]]; then 
    START_COMMAND=$START_COMMAND" --btcnetwork=""$BTC_NETWORK"
fi

$START_COMMAND