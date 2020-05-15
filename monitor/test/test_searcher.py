import json
import os
import pytest

from monitor import MONITOR_DIR, MONITOR_CONF, MONITOR_DEFAULT_CONF
from monitor.searcher import Searcher

from common.config_loader import ConfigLoader

from teos import DATA_DIR, DEFAULT_CONF, CONF_FILE_NAME


test_log_data = [
    {"locator": "bab905e8279395b663bf2feca5213dc5", "message": "New appointment accepted", "time": "01/04/2020 15:53:15"}, 
    {"message": "Shutting down TEOS", "time": "01/04/2020 15:53:31"}
]

conf_loader = ConfigLoader(DATA_DIR, CONF_FILE_NAME, DEFAULT_CONF, {})
conf = conf_loader.build_config()

api_host = conf.get("API_BIND")
api_port = conf.get("API_PORT")
log_file = conf.get("LOG_FILE")

mon_conf_loader = ConfigLoader(MONITOR_DIR, MONITOR_CONF, MONITOR_DEFAULT_CONF, {})
mon_conf = mon_conf_loader.build_config()

es_host = mon_conf.get("ES_HOST")
es_port = mon_conf.get("ES_PORT")
cloud_id = mon_conf.get("CLOUD_ID")
auth_user = mon_conf.get("AUTH_USER")
auth_pw = mon_conf.get("AUTH_PW")



@pytest.fixture(scope="module")
def searcher():
    searcher = Searcher(es_host, es_port, api_host, api_port, DATA_DIR, log_file, cloud_id, auth_user, auth_pw)

    return searcher 


def test_load_logs(searcher): 
    # Create a temporary file with some test logs inside.
    with open("test_log_file", "w") as f:
        for log in test_log_data:
            f.write(json.dumps(log) + "\n")

    # Make sure load_logs function returns the logs in list form. 
    log_data = searcher.load_logs("test_log_file")
    assert len(log_data) == 2

    # Delete the temporary file.
    os.remove("test_log_file")


def test_load_logs_err(searcher):
    # If file doesn't exist, load_logs should throw an error.
    with pytest.raises(FileNotFoundError):
        searcher.load_logs("nonexistent_log_file")

    # TODO: Test if it raises an error if the file is empty.


# NOTE/TODO: Elasticsearch needs to be running for this test to work.
def test_index_data_bulk(searcher):
    json_logs = []
    for log in test_log_data:
        json_logs.append(log)

    response = searcher.index_data_bulk("test-logs", json_logs)
    
    assert type(response) is tuple
    assert len(response) == 2
    assert response[0] == 2

    # Delete test logs from elasticsearch that were indexed.
    searcher.delete_index("test-logs")
    

# TODO: Test that a invalid data sent to index_logs is handled correctly.
