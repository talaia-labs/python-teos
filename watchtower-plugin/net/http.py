import json
import requests
from requests import ConnectionError, ConnectTimeout
from requests.exceptions import MissingSchema, InvalidSchema, InvalidURL

from common import errors
from common import constants
from common.appointment import Appointment
from common.exceptions import SignatureError
from common.cryptographer import Cryptographer

from exceptions import TowerConnectionError, TowerResponseError


def add_appointment(plugin, tower_id, tower, appointment_dict, signature):
    try:
        plugin.log(f"Sending appointment {appointment_dict.get('locator')} to {tower_id}")
        response = send_appointment(tower_id, tower, appointment_dict, signature)
        plugin.log(f"Appointment accepted and signed by {tower_id}")
        plugin.log(f"Remaining slots: {response.get('available_slots')}")

        # # TODO: Not storing the whole appointments for now. The node can recreate all the data if needed.
        # # DISCUSS: It may be worth checking that the available slots match instead of blindly trusting.
        return response.get("signature"), response.get("available_slots")

    except SignatureError as e:
        plugin.log(f"{tower_id} is misbehaving, not using it any longer")
        raise e

    except TowerConnectionError as e:
        plugin.log(f"{tower_id} cannot be reached")

        raise e

    except TowerResponseError as e:
        data = e.kwargs.get("data")
        status_code = e.kwargs.get("status_code")

        if data and status_code == constants.HTTP_BAD_REQUEST:
            if data.get("error_code") == errors.APPOINTMENT_INVALID_SIGNATURE_OR_INSUFFICIENT_SLOTS:
                message = f"There is a subscription issue with {tower_id}"
                raise TowerResponseError(message, status="subscription error")

            elif data.get("error_code") >= errors.INVALID_REQUEST_FORMAT:
                # DISCUSS: It may be worth backing up the data since otherwise the update is dropped
                message = f"Appointment sent to {tower_id} is invalid"
                raise TowerResponseError(message, status="reachable")

        elif status_code == constants.HTTP_SERVICE_UNAVAILABLE:
            # Flag appointment for retry
            message = f"{tower_id} is temporarily unavailable"

            raise TowerResponseError(message, status="temporarily unreachable")

        # Log unexpected behaviour without raising
        plugin.log(str(e), level="warn")


def send_appointment(tower_id, tower, appointment_dict, signature):
    data = {"appointment": appointment_dict, "signature": signature}

    add_appointment_endpoint = f"{tower.netaddr}/add_appointment"
    response = process_post_response(post_request(data, add_appointment_endpoint, tower_id))

    tower_signature = response.get("signature")
    # Check that the server signed the appointment as it should.
    if not tower_signature:
        raise SignatureError("The response does not contain the signature of the appointment", signature=None)

    rpk = Cryptographer.recover_pk(Appointment.from_dict(appointment_dict).serialize(), tower_signature)
    if tower_id != Cryptographer.get_compressed_pk(rpk):
        raise SignatureError(
            "The returned appointment's signature is invalid", tower_id=tower_id, rpk=rpk, signature=tower_signature
        )

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
        message = f"Cannot connect to {tower_id}. Connection timeout"

    except ConnectionError:
        message = f"Cannot connect to {tower_id}. Tower cannot be reached"

    except (InvalidSchema, MissingSchema, InvalidURL):
        message = f"Invalid URL. No schema, or invalid schema, found (url={endpoint}, tower_id={tower_id})"

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
