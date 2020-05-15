from monitor import MONITOR_DIR, MONITOR_CONF, MONITOR_DEFAULT_CONF
from monitor.searcher import Searcher

from common.config_loader import ConfigLoader
from common.logger import Logger

from teos import DATA_DIR, DEFAULT_CONF, CONF_FILE_NAME

LOG_PREFIX = "Main"
logger = Logger(actor="System Monitor Main", log_name_prefix=LOG_PREFIX)

def main(command_line_conf):
    logger.info("Setting up the system monitor.")

    # Pull in Teos's config file to retrieve some of the data we need.
    conf_loader = ConfigLoader(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF, command_line_conf)
    conf = conf_loader.build_config()

    max_users = conf.get("DEFAULT_SLOTS")
    api_host = conf.get("API_BIND")
    api_port = conf.get("API_PORT") 
    log_file = conf.get("LOG_FILE")

    mon_conf_loader = ConfigLoader(MONITOR_DIR, MONITOR_CONF, MONITOR_DEFAULT_CONF, command_line_conf)
    mon_conf = mon_conf_loader.build_config()

    es_host = mon_conf.get("ES_HOST")
    es_port = mon_conf.get("ES_PORT")
    cloud_id = mon_conf.get("CLOUD_ID")
    auth_user = mon_conf.get("AUTH_USER") 
    auth_pw = mon_conf.get("AUTH_PW")

    # Create and start searcher.
    searcher = Searcher(es_host, es_port, api_host, api_port, DATA_DIR, log_file, cloud_id, auth_user, auth_pw)
    searcher.start()

if __name__ == "__main__":
    # TODO:
    command_line_conf = {}

    main(command_line_conf)

