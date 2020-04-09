def show_usage():
    return (
        "USAGE: "
        "\n\tpython teos_cli.py [global options] command [command options] [arguments]"
        "\n\nCOMMANDS:"
        "\n\tregister \tRegisters your user public key with the tower."
        "\n\tadd_appointment \tRegisters a json formatted appointment with the tower."
        "\n\tget_appointment \tGets json formatted data about an appointment from the tower."
        "\n\thelp \t\t\tShows a list of commands or help for a specific command."
        "\n\nGLOBAL OPTIONS:"
        "\n\t--apiconnect \tAPI server where to send the requests. Defaults to 'localhost' (modifiable in conf file)."
        "\n\t--apiport \tAPI port where to send the requests. Defaults to '9814' (modifiable in conf file)."
        "\n\t-d, --debug \tshows debug information and stores it in teos_cli.log."
        "\n\t-h --help \tshows this message."
    )


def help_register():
    return (
        "NAME:"
        "\n\n\tregister"
        "\n\nUSAGE:"
        "\n\n\tpython teos_cli.py register"
        "\n\nDESCRIPTION:"
        "\n\n\tRegisters your user public key with the tower."
    )


def help_add_appointment():
    return (
        "NAME:"
        "\n\tadd_appointment - Registers a json formatted appointment to the tower."
        "\n\nUSAGE:"
        "\n\tpython teos_cli.py add_appointment [command options] appointment/path_to_appointment_file"
        "\n\nDESCRIPTION:"
        "\n\n\tRegisters a json formatted appointment to the tower."
        "\n\tif -f, --file *is* specified, then the command expects a path to a json file instead of a json encoded "
        "\n\tstring as parameter."
        "\n\nOPTIONS:"
        "\n\t -f, --file path_to_json_file\t loads the appointment data from the specified json file instead of"
        "\n\t\t\t\t\t command line"
    )


def help_get_appointment():
    return (
        "NAME:"
        "\n\tget_appointment - Gets json formatted data about an appointment from the tower."
        "\n\nUSAGE:"
        "\n\tpython teos_cli.py get_appointment appointment_locator"
        "\n\nDESCRIPTION:"
        "\n\n\tGets json formatted data about an appointment from the tower.\n"
    )
