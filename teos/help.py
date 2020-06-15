def show_usage():
    return (
        "USAGE: "
        "\n\tpython teosd.py [global options]"
        "\n\nGLOBAL OPTIONS (all modifiable in conf file):"
        "\n\t--apibind \t\taddress that teos API will bind to. Defaults to 'localhost'."
        "\n\t--apiport \t\tport that teos API will bind to. Defaults to '9814'."
        "\n\t--btcnetwork \t\tNetwork bitcoind is connected to. Either mainnet, testnet or regtest. Defaults to "
        "'mainnet'."
        "\n\t--btcrpcuser \t\tbitcoind rpcuser. Defaults to 'user'."
        "\n\t--btcrpcpassword \tbitcoind rpcpassword. Defaults to 'passwd'."
        "\n\t--btcrpcconnect \tbitcoind rpcconnect. Defaults to 'localhost'."
        "\n\t--btcrpcport \t\tbitcoind rpcport. Defaults to '8332'."
        "\n\t--btcfeedconnect \tbitcoind zmq hostname (for blocks). Defaults to 'localhost'."
        "\n\t--btcfeedport \t\tbitcoind zmq port (for blocks). Defaults to '28332'."
        "\n\t--datadir \t\tspecify data directory. Defaults to '~\.teos'."
        "\n\t-h --help \t\tshows this message."
    )
