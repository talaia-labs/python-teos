class InvalidParameter(ValueError):
    """Raised when a command line parameter is invalid (either missing or wrong)"""

    def __init__(self, msg, **kwargs):
        self.reason = msg
        self.kwargs = kwargs


class InvalidKey(Exception):
    """Raised when there is an error loading the keys"""

    def __init__(self, msg, **kwargs):
        self.reason = msg
        self.kwargs = kwargs


class TowerResponseError(Exception):
    """Raised when the tower responds with an error"""

    def __init__(self, msg, **kwargs):
        self.reason = msg
        self.kwargs = kwargs
