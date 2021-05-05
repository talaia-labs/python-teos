import time
import pytest
import threading
from copy import deepcopy
from threading import Event
from coincurve import PrivateKey

from teos.responder import TransactionTracker
from teos.block_processor import BlockProcessor
from teos.extended_appointment import ExtendedAppointment
from teos.internal_api import AuthenticationFailure, NotEnoughSlots

from common.tools import compute_locator
from common.exceptions import InvalidParameter
from common.cryptographer import Cryptographer

from test.teos.conftest import (
    config,
    get_random_value_hex,
)


from test.teos.unit.mocks import (
    Gatekeeper as GatekeeperMock,
    BlockProcessor as BlockProcessorMock,
    AppointmentsDBM as AppointmentsDBManagerMock,
    UsersDBM as UserDBMMock,
    Carrier as CarrierMock,
    Responder as ResponderMock,
)


bitcoind_connect_params = {k: v for k, v in config.items() if k.startswith("BTC")}
wrong_bitcoind_connect_params = deepcopy(bitcoind_connect_params)
wrong_bitcoind_connect_params["BTC_RPC_PORT"] = 1234
bitcoind_feed_params = {k: v for k, v in config.items() if k.startswith("BTC_FEED")}
bitcoind_reachable = Event()
bitcoind_reachable.set()


@pytest.fixture(scope="module")
def block_processor(run_bitcoind):
    return BlockProcessor(bitcoind_connect_params, bitcoind_reachable)


@pytest.fixture(scope="module")
def block_processor_mock():
    return BlockProcessorMock()


@pytest.fixture
def dbm_mock():
    return AppointmentsDBManagerMock()


@pytest.fixture(scope="module")
def user_dbm_mock():
    return UserDBMMock()


@pytest.fixture(scope="module")
def gatekeeper_mock(user_dbm_mock, block_processor_mock):
    return GatekeeperMock(
        user_dbm_mock,
        block_processor_mock,
        config.get("SUBSCRIPTION_SLOTS"),
        config.get("SUBSCRIPTION_DURATION"),
        config.get("EXPIRY_DELTA"),
    )


@pytest.fixture(scope="module")
def carrier_mock():
    return CarrierMock()


@pytest.fixture(scope="module")
def responder_mock():
    return ResponderMock()


@pytest.fixture(scope="session")
def generate_dummy_appointment():
    def _generate_dummy_appointment():
        appointment_data = {
            "locator": get_random_value_hex(16),
            "to_self_delay": 20,
            "encrypted_blob": get_random_value_hex(150),
            "user_id": get_random_value_hex(16),
            "user_signature": get_random_value_hex(50),
            "start_block": 200,
        }

        return ExtendedAppointment.from_dict(appointment_data)

    return _generate_dummy_appointment


@pytest.fixture(scope="session")
def generate_dummy_appointment_w_trigger():
    def _generate_dummy_appointment():
        commitment_txid = get_random_value_hex(32)
        penalty_tx = get_random_value_hex(150)

        appointment_data = {
            "locator": compute_locator(commitment_txid),
            "to_self_delay": 20,
            "encrypted_blob": Cryptographer.encrypt(penalty_tx, commitment_txid),
            "user_id": get_random_value_hex(16),
            "user_signature": get_random_value_hex(50),
            "start_block": 200,
        }

        return ExtendedAppointment.from_dict(appointment_data), commitment_txid

    return _generate_dummy_appointment


@pytest.fixture(scope="session")
def generate_dummy_tracker():
    def _generate_dummy_tracker():
        tracker_data = dict(
            locator=get_random_value_hex(16),
            dispute_txid=get_random_value_hex(32),
            penalty_txid=get_random_value_hex(32),
            penalty_rawtx=get_random_value_hex(150),
            user_id="02" + get_random_value_hex(32),
        )

        return TransactionTracker.from_dict(tracker_data)

    return _generate_dummy_tracker


def generate_keypair():
    sk = PrivateKey()
    pk = sk.public_key

    return sk, pk


# Mocks the return of methods trying to query bitcoind while it cannot be reached
def mock_connection_refused_return(*args, **kwargs):
    raise ConnectionRefusedError()


def raise_invalid_parameter(*args, **kwargs):
    # Message is passed in the API response
    raise InvalidParameter("Invalid parameter message")


def raise_auth_failure(*args, **kwargs):
    raise AuthenticationFailure("Auth failure msg")


def raise_not_enough_slots(*args, **kwargs):
    raise NotEnoughSlots("")


def set_bitcoind_reachable(bitcoind_reachable):
    # Sets the bitcoind_reachable event after a timeout so it can be used to tests the blocking functionality
    time.sleep(2)
    bitcoind_reachable.set()


def run_test_command_bitcoind_crash(command):
    # Test without blocking
    with pytest.raises(ConnectionRefusedError):
        command()


def run_test_blocking_command_bitcoind_crash(event, command):
    # Clear the lock and try it blocking using the valid BlockProcessor
    event.clear()
    t = threading.Thread(target=set_bitcoind_reachable, args=[event])
    t.start()

    # This should not return an exception
    command()
    t.join()
    event.set()
