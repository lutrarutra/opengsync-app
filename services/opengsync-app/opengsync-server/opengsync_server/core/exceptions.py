from opengsync_db.categories import HTTPResponse
from opengsync_db.categories.ExtendedEnum import DBEnum
from abc import ABC, abstractmethod


class OpeNGSyncServerException(Exception, ABC):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

    @property
    @abstractmethod
    def response(self) -> DBEnum:
        pass
        

class NoPermissionsException(OpeNGSyncServerException):
    def __init__(self, message: str = "You don't have permissions to access this resource."):
        super().__init__(message)
    
    @property
    def response(self) -> DBEnum:
        return HTTPResponse.FORBIDDEN


class NotFoundException(OpeNGSyncServerException):
    def __init__(self, message: str = "The resource does not exist."):
        super().__init__(message)

    @property
    def response(self) -> DBEnum:
        return HTTPResponse.NOT_FOUND
    

class BadRequestException(OpeNGSyncServerException):
    def __init__(self, message: str = "The request was invalid or cannot be served."):
        super().__init__(message)

    @property
    def response(self) -> DBEnum:
        return HTTPResponse.BAD_REQUEST
    
    
class MethodNotAllowedException(OpeNGSyncServerException):
    def __init__(self, message: str = "The method is not allowed for the requested URL."):
        super().__init__(message)

    @property
    def response(self) -> DBEnum:
        return HTTPResponse.METHOD_NOT_ALLOWED


class InternalServerErrorException(OpeNGSyncServerException):
    def __init__(self, message: str = "An error occurred while processing your request. Please notify us."):
        super().__init__(message)

    @property
    def response(self) -> DBEnum:
        return HTTPResponse.INTERNAL_SERVER_ERROR