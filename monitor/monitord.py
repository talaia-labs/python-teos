import json
import os
from elasticsearch import Elasticsearch, helpers
from elasticsearch.helpers.errors import BulkIndexError

from log import LOG_PREFIX
from common.logger import Logger

logger = Logger(actor="System Monitor", log_name_prefix=LOG_PREFIX)



es = Elasticsearch()

log_path = os.path.expanduser("~/.teos/teos.log")


# TODO: Logs are constantly being updated. Should we keep that data updated?
def load_logs(log_path):
    """ 
    Reads teos log into a list.

    Returns:
        :obj:`list`: The logs in the form of a list.

    Raises:
        FileNotFoundError: If path doesn't correspond to an existing log file.
        
    """

    # Load the initial log file.
    with open(log_path, "r") as log_file:
        log_data = log_file.readlines()
        return log_data

    # TODO: Throw an error if the file is empty or if data isn't JSON.


def gen_log_data(log_data):
    """ 
    Formats logs so it can be sent to Elasticsearch in bulk.

    Args:
        log_data (:obj:`list`): The logs in list form.

    Yields:
        :obj:`dict`: A dict conforming to the required format for sending data to elasticsearch in bulk.
    """

    for log in log_data:
        yield {
            "_index": "logs",
            "_type": "document",
            "doc": {"log": log},
        }

def index_logs(log_data):
    """ 
    Indexes logs in elasticsearch so they can be searched.

    Args:
        logs (:obj:`str`): The logs in JSON form.

    Returns:
        response (:obj:`tuple`): The first value of the tuple equals the number of the logs data was entered successfully. If there are errors the second value in the tuple includes the errors.

    Raises: 
        elasticsearch.helpers.errors.BulkIndexError: Returned by Elasticsearch if indexing log data fails.
        
    """

    response = helpers.bulk(es, gen_log_data(log_data))

    # The response is a tuple of two items: 1) The number of items successfully indexed. 2) Any errors returned.

    if response[0] == 0:
        logger.error("Indexing logs in Elasticsearch error: ", e) 
        raise BulkIndexError()

    return response


def main():
    logger.info("Setting up the system monitor.")

    log_data = load_logs(log_path)

    index_logs(log_data)

if __name__ == "__main__":
    main()
