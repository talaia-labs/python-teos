class BasicException(Exception):
    """Base exception for all the other custom ones. Allows to store a message and some ``kwargs``."""

    def __init__(self, msg, **kwargs):
        self.msg = msg
        self.kwargs = kwargs

    def __str__(self):
        if len(self.kwargs) > 2:
            params = "".join("{}={}, ".format(k, v) for k, v in self.kwargs.items())

            # Remove the extra 2 characters (space and comma) and add all data to the final message.
            message = self.msg + " ({})".format(params[:-2])

        else:
            message = self.msg

        return message

    def to_json(self):
        return {"error": self.msg, **self.kwargs}


class InvalidParameter(BasicException):
    """Raised when a command line parameter is invalid (either missing or wrong)."""


class InvalidKey(BasicException):
    """Raised when there is an error loading the keys."""


class EncryptionError(BasicException):
    """Raised when there is an error with encryption related functions, covers decryption."""


class SignatureError(BasicException):
    """Raised when there is an with the signature related functions, covers EC recover."""


class TowerConnectionError(BasicException):
    """Raised when the tower responds with an error."""


class TowerResponseError(BasicException):
    """Raised when the tower responds with an error."""
