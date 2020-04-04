import json
import os
from elasticsearch import Elasticsearch

es = Elasticsearch()

log_path = os.path.expanduser("~/.teos/teos.log")

# Need to keep reading the file as it grows. 
def load_logs():
    """ 
    Reads teos log as JSON. Reads initial file, then 

    Returns:
    """

    # Load the initial log file.
    with open(log_path, "r") as log_file:
        log_data = log_file.readlines()

        try:
            log_json = json.dumps(log_data)
        except TypeError:
            print("Unable to serialize logs to JSON.")

# Keep parsing data from constantly updating logs.
#   with open(log_path, "r") as log_file:
#       for line in tail(log_file):
#           try:
#               log_data = json.loads(line)
#           except ValueError:
#               continue  # Read next line

def main():
    load_logs()

if __name__ == "__main__":
    main()

