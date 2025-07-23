from opengsync_db.categories import HTTPResponse
from opengsync_db.categories.ExtendedEnum import DBEnum
from abc import ABC, abstractmethod


class OpenGSyncException(Exception, ABC):
    @property
    @abstractmethod
    def response(self) -> DBEnum:
        pass
        

class NoPermissionsException(OpenGSyncException):
    @property
    def response(self) -> DBEnum:
        return HTTPResponse.FORBIDDEN


class NotFoundException(OpenGSyncException):
    @property
    def response(self) -> DBEnum:
        return HTTPResponse.NOT_FOUND


class InternalServerErrorException(OpenGSyncException):
    @property
    def response(self) -> DBEnum:
        return HTTPResponse.INTERNAL_SERVER_ERROR
    
    
class WorkflowException(OpenGSyncException):
    @property
    def response(self) -> DBEnum:
        return HTTPResponse.INTERNAL_SERVER_ERROR