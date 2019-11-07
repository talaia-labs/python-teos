def help_add_appointment():
    return (
        "NAME:"
        "\tpython pisa-cli add_appointment - Registers a json formatted appointment to the PISA server."
        "\n\nUSAGE:"
        "\tpython pisa-cli add_appointment [command options] appointment/path_to_appointment_file"
        "\n\nDESCRIPTION:"
        "\n\n\tRegisters a json formatted appointment to the PISA server."
        "\n\tif -f, --file *is* specified, then the command expects a path to a json file instead of a json encoded "
        "\n\tstring as parameter."
        "\n\nOPTIONS:"
        "\n\t -f, --file path_to_json_file\t loads the appointment data from the specified json file instead of"
        "\n\t\t\t\t\t command line"
    )


def help_get_appointment():
    return (
        "NAME:"
        "\tpython pisa-cli get_appointment - Gets json formatted data about an appointment from the PISA server."
        "\n\nUSAGE:"
        "\tpython pisa-cli get_appointment appointment_locator"
        "\n\nDESCRIPTION:"
        "\n\n\tGets json formatted data about an appointment from the PISA server.\n"
    )
