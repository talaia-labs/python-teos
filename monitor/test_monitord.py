import json
import os
import pytest

from monitor.monitord import load_logs, gen_log_data, index_logs

test_log_data = [
    {"locator": "bab905e8279395b663bf2feca5213dc5", "message": "New appointment accepted", "time": "01/04/2020 15:53:15"}, 
    {"message": "Shutting down TEOS", "time": "01/04/2020 15:53:31"}
]



def test_load_logs(): 
    # Create a temporary file with some test logs inside.
    with open("test_log_file", "w") as f:
        for log in test_log_data:
            f.write(json.dumps(log) + "\n")

    # Make sure load_logs function returns the logs in list form. 
    log_data = load_logs("test_log_file")
    assert len(log_data) == 2

    # Delete the temporary file.
    os.remove("test_log_file")


def test_load_logs_err():
    # If file doesn't exist, load_logs should throw an error.
    with pytest.raises(FileNotFoundError):
        load_logs("nonexistent_log_file")

    # TODO: Test if it raises an error if the file is empty.


# NOTE/TODO: Elasticsearch needs to be running for this test to work.
def test_index_logs():
    json_logs = []
    for log in test_log_data:
        json_logs.append(log)

    response = index_logs(json_logs)
    
    assert type(response) is tuple
    assert len(response) == 2
    assert response[0] == 2

    # TODO: Delete logs from elasticsearch that were indexed
    

# TODO: Test that a invalid data sent to index_logs is handled correctly.

