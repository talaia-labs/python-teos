import json
import requests
from requests import ConnectionError, ConnectTimeout
from requests.exceptions import MissingSchema, InvalidSchema, InvalidURL

from common import constants
from common.appointment import Appointment
from common.cryptographer import Cryptographer

from exceptions import TowerConnectionError, TowerResponseError


def send_appointment(tower_id, tower_info, appointment_dict, signature):
    data = {"appointment": appointment_dict, "signature": signature}

    add_appointment_endpoint = "{}/add_appointment".format(tower_info.netaddr)
    response = process_post_response(post_request(data, add_appointment_endpoint, tower_id))

    signature = response.get("signature")
    # Check that the server signed the appointment as it should.
    if not signature:
        raise TowerResponseError("The response does not contain the signature of the appointment")

    rpk = Cryptographer.recover_pk(Appointment.from_dict(appointment_dict).serialize(), signature)
    if not tower_id != Cryptographer.get_compressed_pk(rpk):
        raise TowerResponseError("The returned appointment's signature is invalid")

    return response


def post_request(data, endpoint, tower_id):
    """
    Sends a post request to the tower.

    Args:
        data (:obj:`dict`): a dictionary containing the data to be posted.
        endpoint (:obj:`str`): the endpoint to send the post request.
        tower_id (:obj:`str`): the identifier of the tower to connect to (a compressed public key).

    Returns:
        :obj:`dict`: a json-encoded dictionary with the server response if the data can be posted.

    Raises:
        :obj:`ConnectionError`: if the client cannot connect to the tower.
    """

    try:
        return requests.post(url=endpoint, json=data, timeout=5)

    except ConnectTimeout:
        message = "Cannot connect to {}. Connection timeout".format(tower_id)

    except ConnectionError:
        message = "Cannot connect to {}. Tower cannot be reached".format(tower_id)

    except (InvalidSchema, MissingSchema, InvalidURL):
        message = "Invalid URL. No schema, or invalid schema, found (url={}, tower_id={}).".format(endpoint, tower_id)

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
