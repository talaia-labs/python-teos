import json
import os
from elasticsearch import Elasticsearch, helpers
from elasticsearch.client import IndicesClient
from elasticsearch.helpers.errors import BulkIndexError

from common.logger import Logger

LOG_PREFIX = "System Monitor"
logger = Logger(actor="Searcher", log_name_prefix=LOG_PREFIX)


class Searcher:
    """ 
    The :class:`Searcher` is in charge of the monitor's Elasticsearch functionality for loading and searching through data.
    
    Args:
        host (:obj:`str`): The host Elasticsearch is running on.
        port (:obj:`int`): The port Elasticsearch is runnning on.
        cloud_id (:obj:`str`): Elasticsearch cloud id, if Elasticsearch Cloud is being used.
        auth_user (:obj:`str`): Elasticsearch Cloud username, if Elasticsearch Cloud is being used.
        auth_pw (:obj:`str`): Elasticsearch Cloud password, if Elasticsearch Cloud is being used.

    Attributes:
        host (:obj:`str`): The host Elasticsearch is running on.
        port (:obj:`int`): The port Elasticsearch is runnning on.
        cloud_id (:obj:`str`): Elasticsearch cloud id, if Elasticsearch Cloud is being used.
        auth_user (:obj:`str`): Elasticsearch Cloud username, if Elasticsearch Cloud is being used.
        auth_pw (:obj:`str`): Elasticsearch Cloud password, if Elasticsearch Cloud is being used.
        es (:obj:`Elasticsearch <elasticsearch.Elasticsearch>`): The Elasticsearch client for searching for data to be visualized.
        index_client (:obj:`IndicesClient <elasticsearch.client.IndiciesClient>`): The index client where log data is stored.
        log_path (:obj:`str`): The path to the log file where log file will be pulled from and analyzed by ES.
    
    """

    def __init__(self, host, port, cloud_id=None, auth_user=None, auth_pw=None):
         self.es_host = host
         self.es_port = port
         self.es_cloud_id = cloud_id
         self.es_auth_user = auth_user
         self.es_auth_pw = auth_pw
         self.es = Elasticsearch(
             cloud_id=self.es_cloud_id,
             http_auth=(self.es_auth_user, self.es_auth_pw),
         )
         self.index_client = IndicesClient(self.es)
         # TODO: Pass the path through as a config option.
         self.log_path = os.path.expanduser("~/.teos/teos_test.log") 

    def start(self):
        """Starts Elasticsearch and compiles data to be visualized in Kibana"""

        # Pull the watchtower logs into Elasticsearch.
        # self.index_client.delete("logs")
        # self.create_log_index("logs") 
        # log_data = self.load_logs(self.log_path)
        # self.index_logs(log_data)

        # Search for the data we need to visualize a graph.

        # self.search_logs("message", ["logs"])
        self.get_all_logs()
        # self.delete_all_by_index("logs")

    def create_log_index(self, index):
        """ 
        Create index with a particular mapping.
    
        Args:
            index (:obj:`str`): Index the mapping is in.

        """

        body = {
            "mappings": {
                "properties": {
                    "doc.time": {
                        "type": "date",
                        "format": "strict_date_optional_time||dd/MM/yyyy HH:mm:ss"
                    }
                }
            }
        }
        self.index_client.create(index, body)
         
    # TODO: Logs are constantly being updated. Keep that data updated
    def load_logs(self, log_path):
        """ 
        Reads teos log into a list.
    
        Args:
            log_path (:obj:`str`): The path to the log file.
    
        Returns:
            :obj:`list`: A list of logs in dict form.
    
        Raises:
            FileNotFoundError: If path doesn't correspond to an existing log file.
            
        """
    
        # Load the initial log file.
        logs = []
        with open(log_path, "r") as log_file:
            for log in log_file:
                log_data = json.loads(log.strip())
                logs.append(log_data)

        return logs
    
        # TODO: Throw an error if the file is empty or if data isn't JSON-y.
    
    @staticmethod 
    def gen_log_data(log_data):
        """ 
        Formats logs so it can be sent to Elasticsearch in bulk.
    
        Args:
            log_data (:obj:`list`): A list of logs in dict form.
    
        Yields:
            :obj:`dict`: A dict conforming to the required format for sending data to elasticsearch in bulk.
        """
    
        for log in log_data:
            # We don't need to include errors (which had problems mapping anyway)
            # if 'error' in log:
            #    continue
            yield {
                "_index": "logs",
                # "_type": "document",
                "doc": log
            }
    
    
    def index_logs(self, log_data):
        """ 
        Indexes logs in elasticsearch so they can be searched.
    
        Args:
            logs (:obj:`list`): A list of logs in dict form.
    
        Returns:
            response (:obj:`tuple`): The first value of the tuple equals the number of the logs data was entered successfully. If there are errors the second value in the tuple includes the errors.
    
        Raises: 
            elasticsearch.helpers.errors.BulkIndexError: Returned by Elasticsearch if indexing log data fails.
            
        """
    
        response = helpers.bulk(self.es, self.gen_log_data(log_data))
    
        # The response is a tuple of two items: 1) The number of items successfully indexed. 2) Any errors returned.
        if (response[0] <= 0):
            logger.error("None of the logs were indexed. Log data might be in the wrong form.") 

        return response

    def search_logs(self, field, keyword, index):
        """ 
        Searches Elasticsearch for data with a certain field and keyword.
    
        Args:
            field (:obj:`str`): The search field. 
            keyword (:obj:`str`): The search keyword. 
            index (:obj:`str`): The index in Elasticsearch to search through.
    
        Returns:
            :obj:`dict`: A dict describing the results, including the first 10 docs matching the search words. 
        """
    
        body = {
            "query": {"match": {"doc.{}".format(field): keyword}} 
        }
        results = self.es.search(body, index) 
    
        return results
    
    
    def get_all_logs(self):
        """ 
        Retrieves all logs in the logs index of Elasticsearch.
    
        Returns:
            :obj:`dict`: A dict describing the results, including the first 10 docs. 
        """
    
        body = {
            "query": { "match_all": {} }
        }
        results = self.es.search(body, "logs") 
    
        results = json.dumps(results, indent=4)
    
        return results
    
    
    def delete_all_by_index(self, index):
        """ 
        Deletes all logs in the chosen index of Elasticsearch.
    
        Args:
            index (:obj:`str`): The index in Elasticsearch.
    
        Returns:
            :obj:`dict`: A dict describing how many items were deleted and including any deletion failures.
    
        """
    
        body = { 
            "query": { "match_all": {} }
        }   
        results = self.es.delete_by_query(index, body) 
      
        return results