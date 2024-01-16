class InvalidValue(Exception):
    pass

class LinkDoesNotExist(Exception):
    pass


class ElementDoesNotExist(Exception):
    pass


class LinkAlreadyExists(Exception):
    pass


class InvalidRole(Exception):
    pass


class NotUniqueValue(Exception):
    pass


class ElementIsReferenced(Exception):
    pass


class FileExistsException(Exception):
    def __init__(self, file_path):
        self.message = f"File '{file_path}' already exists..."
