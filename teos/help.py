def show_usage():
    return (
        "USAGE: "
        "\n\tpython teosd.py [global options]"
        "\n\nGLOBAL OPTIONS:"
        "\n\t--apibind \t\taddress that teos API will bind to. Defaults to 'localhost' (modifiable in conf file)."
        "\n\t--apiport \t\tport that teos API will bind to. Defaults to '9814' (modifiable in conf file)."
        "\n\t--btcnetwork \t\tNetwork bitcoind is connected to. Either mainnet, testnet or regtest. Defaults to "
        "'mainnet' (modifiable in conf file)."
        "\n\t--btcrpcuser \t\tbitcoind rpcuser. Defaults to 'user' (modifiable in conf file)."
        "\n\t--btcrpcpassword \tbitcoind rpcpassword. Defaults to 'passwd' (modifiable in conf file)."
        "\n\t--btcrpcconnect \tbitcoind rpcconnect. Defaults to 'localhost' (modifiable in conf file)."
        "\n\t--btcrpcport \t\tbitcoind rpcport. Defaults to '8332' (modifiable in conf file)."
        "\n\t--datadir \t\tspecify data directory. Defaults to '~\.teos' (modifiable in conf file)."
        "\n\t-h --help \t\tshows this message."
    )
