def show_usage():
    return (
        "USAGE: "
        "\n\tpython teos_cli.py [global options] command [command options] [arguments]"
        "\n\nCOMMANDS:"
        "\n\tget_all_appointments \tGets information about all appointments stored in the tower."
        "\n\tget_tower_info \tGets generic information about the tower."
        "\n\tget_users \tGets the list of registered user ids."
        "\n\tget_user \tGets information about a specific user."
        "\n\thelp \t\t\tShows a list of commands or help for a specific command."
        "\n\nGLOBAL OPTIONS:"
        "\n\t--rpcconnect \tRPC server where to send the requests. Defaults to 'localhost' (modifiable in conf file)."
        "\n\t--rpcport \tRPC port where to send the requests. Defaults to '8814' (modifiable in conf file)."
        "\n\t-d, --debug \tShows debug information and stores it in teos_cli.log."
        "\n\t-h, --help \tShows this message."
    )


def help_get_all_appointments():
    return (
        "NAME:"
        "\tpython teos_cli get_all_appointments - Gets information about all the appointments stored in the tower."
        "\n\nUSAGE:"
        "\tpython teos_cli.py get_all_appointments"
        "\n\nDESCRIPTION:"
        "\n\n\tGets information about all appointments stored in the tower.\n"
    )


def help_get_tower_info():
    return (
        "NAME:"
        "\tpython teos_cli get_tower_info - Gets generic information about the tower."
        "\n\nUSAGE:"
        "\tpython teos_cli.py get_tower_info"
        "\n\nDESCRIPTION:"
        "\n\n\tGets generic information about the tower, like tower_id and aggregate data on users and appointments.\n"
    )


def help_get_users():
    return (
        "NAME:"
        "\tpython teos_cli get_users - Gets the list of registered user ids."
        "\n\nUSAGE:"
        "\tpython teos_cli.py get_users"
        "\n\nDESCRIPTION:"
        "\n\n\tGets an array with the user ids of all the users registered to the tower.\n"
    )


def help_get_user():
    return (
        "NAME:"
        "\tpython teos_cli get_user - Gets information about a specific user."
        "\n\nUSAGE:"
        '\tpython teos_cli.py get_user "user_id"'
        "\n\nDESCRIPTION:"
        "\n\n\tGets information about a specific user.\n"
    )


def help_stop():
    return (
        "NAME:"
        "\tpython teos_cli stop - Requests a graceful shutdown of the tower."
        "\n\nUSAGE:"
        "\tpython teos_cli.py stop"
        "\n\nDESCRIPTION:"
        "\n\n\Requests a graceful shutdown of the tower.\n"
    )
