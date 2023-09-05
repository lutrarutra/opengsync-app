class LinkDoesNotExist(Exception):
    def __init__(self, message):
        super().__init__(message)


class ElementDoesNotExist(Exception):
    def __init__(self, message):
        super().__init__(message)


class LinkAlreadyExists(Exception):
    def __init__(self, message):
        super().__init__(message)


class InvalidRole(Exception):
    def __init__(self, message):
        super().__init__(message)


class NotUniqueValue(Exception):
    def __init__(self, message):
        super().__init__(message)


class FileExistsException(Exception):
    def __init__(self, file_path):
        self.message = f"File '{file_path}' already exists..."
