class OpeNGSyncDBException(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class RollBackTriggered(OpeNGSyncDBException):
    def __init__(self, message: str = "DB Rollback Triggered"):
        super().__init__(message)


class InvalidValue(OpeNGSyncDBException):
    def __init__(self, message: str = "Invalid Value"):
        super().__init__(message)


class LinkDoesNotExist(OpeNGSyncDBException):
    def __init__(self, message: str = "Link Does Not Exist"):
        super().__init__(message)


class ElementDoesNotExist(OpeNGSyncDBException):
    def __init__(self, message: str = "Element Does Not Exist"):
        super().__init__(message)


class LinkAlreadyExists(OpeNGSyncDBException):
    def __init__(self, message: str = "Link Already Exists"):
        super().__init__(message)


class NotUniqueValue(OpeNGSyncDBException):
    def __init__(self, message: str = "Value breaks not unique-constraint"):
        super().__init__(message)


class ElementIsReferenced(OpeNGSyncDBException):
    def __init__(self, message: str = "Element Is Referenced"):
        super().__init__(message)


class InvalidOperation(OpeNGSyncDBException):
    def __init__(self, message: str = "Invalid Operation"):
        super().__init__(message)


class FileExistsException(OpeNGSyncDBException):
    def __init__(self, message: str = "File already exists"):
        self.message = message
