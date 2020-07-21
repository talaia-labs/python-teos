from common.exceptions import BasicException


class TowerConnectionError(BasicException):
    """Raised when the tower responds with an error"""


class TowerResponseError(BasicException):
    """Raised when the tower responds with an error"""
