import os
import apps.cli.conf as conf
from common.tools import extend_paths, check_conf_fields, setup_logging, setup_data_folder

LOG_PREFIX = "cli"

# Load config fields
conf_fields = {
    "DEFAULT_PISA_API_SERVER": {"value": conf.DEFAULT_PISA_API_SERVER, "type": str},
    "DEFAULT_PISA_API_PORT": {"value": conf.DEFAULT_PISA_API_PORT, "type": int},
    "DATA_FOLDER": {"value": conf.DATA_FOLDER, "type": str},
    "CLIENT_LOG_FILE": {"value": conf.CLIENT_LOG_FILE, "type": str, "path": True},
    "APPOINTMENTS_FOLDER_NAME": {"value": conf.APPOINTMENTS_FOLDER_NAME, "type": str, "path": True},
    # "CLI_PUBLIC_KEY": {"value": conf.CLI_PUBLIC_KEY, "type": str, "path": True},
    # "CLI_PRIVATE_KEY": {"value": conf.CLI_PRIVATE_KEY, "type": str, "path": True},
    # "PISA_PUBLIC_KEY": {"value": conf.PISA_PUBLIC_KEY, "type": str, "path": True},
}

# Expand user (~) if found and check fields are correct
conf_fields["DATA_FOLDER"]["value"] = os.path.expanduser(conf_fields["DATA_FOLDER"]["value"])
# Extend relative paths
conf_fields = extend_paths(conf_fields["DATA_FOLDER"]["value"], conf_fields)

# Sanity check fields and build config dictionary
config = check_conf_fields(conf_fields)

setup_data_folder(config.get("DATA_FOLDER"))
setup_logging(config.get("CLIENT_LOG_FILE"), LOG_PREFIX)
