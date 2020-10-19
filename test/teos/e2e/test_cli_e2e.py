import pytest
import json
from time import sleep

from contrib.client import teos_client

from common.exceptions import InvalidParameter
from common.cryptographer import Cryptographer

from teos.cli.rpc_client import RPCClient

from test.teos.conftest import (
    create_txs,
    generate_block_with_transactions,
    generate_blocks,
    config,
)
from test.teos.e2e.conftest import build_appointment_data

teos_base_endpoint = "http://{}:{}".format(config.get("API_BIND"), config.get("API_PORT"))

user_sk = Cryptographer.generate_key()
user_id = Cryptographer.get_compressed_pk(user_sk.public_key)


@pytest.fixture
def rpc_client():
    return RPCClient(config.get("RPC_BIND"), config.get("RPC_PORT"))


def get_appointment_info(teos_id, locator, sk=user_sk):
    sleep(1)  # Let's add a bit of delay so the state can be updated
    return teos_client.get_appointment(locator, sk, teos_id, teos_base_endpoint)


def add_appointment(teos_id, appointment_data, sk=user_sk):
    return teos_client.add_appointment(appointment_data, sk, teos_id, teos_base_endpoint)


def test_get_all_appointments(teosd, rpc_client):
    _, teos_id = teosd

    # Check that there is no appointment, so far
    all_appointments = json.loads(rpc_client.get_all_appointments())
    watching = all_appointments.get("watcher_appointments")
    responding = all_appointments.get("responder_trackers")
    assert len(watching) == 0 and len(responding) == 0

    # Register a user
    teos_client.register(user_id, teos_id, teos_base_endpoint)

    # After that we can build an appointment and send it to the tower
    commitment_tx, commitment_txid, penalty_tx = create_txs()
    appointment_data = build_appointment_data(commitment_txid, penalty_tx)
    appointment = teos_client.create_appointment(appointment_data)
    add_appointment(teos_id, appointment)

    # Now there should now be one appointment in the watcher
    all_appointments = json.loads(rpc_client.get_all_appointments())
    watching = all_appointments.get("watcher_appointments")
    responding = all_appointments.get("responder_trackers")
    assert len(watching) == 1 and len(responding) == 0

    # Trigger a breach and check again; now the appointment should be in the responder
    generate_block_with_transactions(commitment_tx)
    sleep(1)

    all_appointments = json.loads(rpc_client.get_all_appointments())
    watching = all_appointments.get("watcher_appointments")
    responding = all_appointments.get("responder_trackers")
    assert len(watching) == 0 and len(responding) == 1

    # Now let's mine some blocks so the appointment reaches its end. We need 100 + EXPIRY_DELTA -1
    generate_blocks(100 + config.get("EXPIRY_DELTA"))
    sleep(1)

    # Now the appointment should not be in the tower, back to 0
    all_appointments = json.loads(rpc_client.get_all_appointments())
    watching = all_appointments.get("watcher_appointments")
    responding = all_appointments.get("responder_trackers")
    assert len(watching) == 0 and len(responding) == 0


def test_get_tower_info(teosd, rpc_client):
    tower_info = json.loads(rpc_client.get_tower_info())
    assert set(tower_info.keys()) == set(
        ["n_registered_users", "tower_id", "n_watcher_appointments", "n_responder_trackers"]
    )


def test_get_users(teosd, rpc_client):
    _, teos_id = teosd

    # Create a fresh user
    tmp_user_id = Cryptographer.get_compressed_pk(Cryptographer.generate_key().public_key)

    users = json.loads(rpc_client.get_users())
    assert tmp_user_id not in users

    # Register the fresh user
    teos_client.register(tmp_user_id, teos_id, teos_base_endpoint)

    users = json.loads(rpc_client.get_users())
    assert tmp_user_id in users


def test_get_user(teosd, rpc_client):
    _, teos_id = teosd

    # Register a user
    available_slots, subscription_expiry = teos_client.register(user_id, teos_id, teos_base_endpoint)

    # Get back its info
    user = json.loads(rpc_client.get_user(user_id))

    assert set(user.keys()) == set(["appointments", "available_slots", "subscription_expiry"])
    assert user["available_slots"] == available_slots
    assert user["subscription_expiry"] == subscription_expiry


def test_get_user_non_existing(teosd, rpc_client):
    # Get a user that does not exist
    with pytest.raises(InvalidParameter):
        rpc_client.get_user("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff00")
