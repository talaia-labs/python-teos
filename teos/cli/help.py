def show_usage():
    return (
        "USAGE: "
        "\n\tpython teos_cli.py [global options] command [command options] [arguments]"
        "\n\nCOMMANDS:"
        "\n\tget_all_appointments \tGets information about all appointments stored in the tower."
        "\n\thelp \t\t\tShows a list of commands or help for a specific command."
        "\n\nGLOBAL OPTIONS:"
        "\n\t--rpcconnect \tRPC server where to send the requests. Defaults to 'localhost' (modifiable in conf file)."
        "\n\t--rpcport \tRPC port where to send the requests. Defaults to '9000' (modifiable in conf file)."
        "\n\t-d, --debug \tShows debug information and stores it in teos_cli.log."
        "\n\t-h, --help \tShows this message."
    )


def help_get_all_appointments():
    return (
        "NAME:"
        "\tpython teos_cli get_all_appointments - Gets information about all appointments stored in the tower."
        "\n\nUSAGE:"
        "\tpython teos_cli.py get_all_appointments"
        "\n\nDESCRIPTION:"
        "\n\n\tGets information about all appointments stored in the tower.\n"
    )
