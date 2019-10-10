from pisa.tools import check_txid_format
from pisa import logging

logging.getLogger().disabled = True


def test_check_txid_format():
    assert(check_txid_format(None) is False)
    assert(check_txid_format("") is False)
    assert(check_txid_format(0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef) is False)  # wrong type
    assert(check_txid_format("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef") is True)  # lowercase
    assert(check_txid_format("0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF") is True)  # uppercase
    assert(check_txid_format("0123456789abcdef0123456789ABCDEF0123456789abcdef0123456789ABCDEF") is True)  # mixed case
    assert(check_txid_format("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdf") is False)  # too short
    assert(check_txid_format("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0") is False)  # too long
    assert(check_txid_format("g123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef") is False)  # non-hex
