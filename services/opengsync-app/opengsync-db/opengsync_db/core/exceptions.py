class OpeNGSyncDBException(Exception):
    pass


class RollBackTriggered(OpeNGSyncDBException):
    pass


class InvalidValue(OpeNGSyncDBException):
    pass


class LinkDoesNotExist(OpeNGSyncDBException):
    pass


class ElementDoesNotExist(OpeNGSyncDBException):
    pass


class LinkAlreadyExists(OpeNGSyncDBException):
    pass


class InvalidRole(OpeNGSyncDBException):
    pass


class NotUniqueValue(OpeNGSyncDBException):
    pass


class ElementIsReferenced(OpeNGSyncDBException):
    pass


class InvalidOperation(OpeNGSyncDBException):
    pass


class FileExistsException(OpeNGSyncDBException):
    def __init__(self, file_path):
        self.message = f"File '{file_path}' already exists..."
