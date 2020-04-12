import json
import os
from elasticsearch import Elasticsearch, helpers
from elasticsearch.helpers.errors import BulkIndexError

from common.logger import Logger

LOG_PREFIX = "System Monitor"
logger = Logger(actor="Searcher", log_name_prefix=LOG_PREFIX)


class Searcher:
    def __init__(self):
         self.es = Elasticsearch()
         # TODO: Pass the path through as a config option.
         self.log_path = os.path.expanduser("~/.teos/teos.log") 

    def start(self):
        # Pull the watchtower logs into Elasticsearch.
        log_data = self.load_logs(log_path)
        self.index_logs(log_data)

        # Search for the data we need to visualize a graph.

        # self.search_logs("message", ["logs"])
        # self.get_all_logs()
        # self.delete_all_by_index("logs")
         
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
            if 'error' in log:
                continue
            yield {
                "_index": "logs",
                "_type": "document",
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
        # print("response: ", response)
    
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
