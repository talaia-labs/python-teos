import json
import requests
from requests import ConnectionError, ConnectTimeout
from requests.exceptions import MissingSchema, InvalidSchema, InvalidURL

from common import constants
from exceptions import TowerConnectionError, TowerResponseError


def post_request(data, endpoint):
    """
    Sends a post request to the tower.

    Args:
        data (:obj:`dict`): a dictionary containing the data to be posted.
        endpoint (:obj:`str`): the endpoint to send the post request.

    Returns:
        :obj:`dict`: a json-encoded dictionary with the server response if the data can be posted.

    Raises:
        :obj:`ConnectionError`: if the client cannot connect to the tower.
    """

    try:
        return requests.post(url=endpoint, json=data, timeout=5)

    except ConnectTimeout:
        message = "Cannot connect to the Eye of Satoshi at {}. Connection timeout".format(endpoint)

    except ConnectionError:
        message = "Cannot connect to the Eye of Satoshi at {}. Tower cannot be reached".format(endpoint)

    except (InvalidSchema, MissingSchema, InvalidURL):
        message = "Invalid URL. No schema, or invalid schema, found ({})".format(endpoint)

    raise TowerConnectionError(message)


def process_post_response(response):
    """
    Processes the server response to a post request.

    Args:
        response (:obj:`requests.models.Response`): a ``Response`` object obtained from the request.

    Returns:
        :obj:`dict`: a dictionary containing the tower's response data if the response type is
        ``HTTP_OK``.

    Raises:
        :obj:`TowerResponseError <cli.exceptions.TowerResponseError>`: if the tower responded with an error, or the
        response was invalid.
    """

    try:
        response_json = response.json()

    except (json.JSONDecodeError, AttributeError):
        raise TowerResponseError(
            "The server returned a non-JSON response", status_code=response.status_code, reason=response.reason
        )

    if response.status_code not in [constants.HTTP_OK, constants.HTTP_NOT_FOUND]:
        raise TowerResponseError(
            "The server returned an error", status_code=response.status_code, reason=response.reason, data=response_json
        )

    return response_json
