#!/bin/bash 

START_COMMAND="teosd "

if [[ ! -z ${API_BIND} ]]; then
    START_COMMAND=$START_COMMAND" --apibind=""$API_BIND"
fi

if [[ ! -z ${API_PORT} ]]; then
    START_COMMAND=$START_COMMAND" --apiport=""$API_PORT"
fi

if [[ ! -z ${RPC_BIND} ]]; then
    START_COMMAND=$START_COMMAND" --rpcbind=""$RPC_BIND"
fi

if [[ ! -z ${RPC_PORT} ]]; then
    START_COMMAND=$START_COMMAND" --rpcport=""$RPC_PORT"
fi

if [[ ! -z ${BTC_NETWORK} ]]; then
    START_COMMAND=$START_COMMAND" --btcnetwork=""$BTC_NETWORK"
fi

if [[ ! -z ${BTC_RPC_USER} ]]; then 
    START_COMMAND=$START_COMMAND" --btcrpcuser=""$BTC_RPC_USER"
fi

if [[ ! -z ${BTC_RPC_PASSWORD} ]]; then
    START_COMMAND=$START_COMMAND" --btcrpcpassword=""$BTC_RPC_PASSWORD"
fi

if [[ ! -z ${BTC_RPC_CONNECT} ]]; then
    START_COMMAND=$START_COMMAND" --btcrpcconnect=""$BTC_RPC_CONNECT"
fi

if [[ ! -z ${BTC_RPC_PORT} ]]; then
    START_COMMAND=$START_COMMAND" --btcrpcport=""$BTC_RPC_PORT"
fi

if [[ ! -z ${BTC_FEED_CONNECT} ]]; then
    START_COMMAND=$START_COMMAND" --btcfeedconnect=""$BTC_FEED_CONNECT"
fi

if [[ ! -z ${BTC_FEED_PORT} ]]; then
    START_COMMAND=$START_COMMAND" --btcfeedport=""$BTC_FEED_PORT"
fi

$START_COMMAND
