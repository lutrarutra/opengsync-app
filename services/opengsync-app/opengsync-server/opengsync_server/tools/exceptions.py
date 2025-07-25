from opengsync_db.categories import HTTPResponse
from opengsync_db.categories.ExtendedEnum import DBEnum
from abc import ABC, abstractmethod


class OpeNGSyncServerException(Exception, ABC):
    @property
    @abstractmethod
    def response(self) -> DBEnum:
        pass
        

class NoPermissionsException(OpeNGSyncServerException):
    @property
    def response(self) -> DBEnum:
        return HTTPResponse.FORBIDDEN


class NotFoundException(OpeNGSyncServerException):
    @property
    def response(self) -> DBEnum:
        return HTTPResponse.NOT_FOUND


class InternalServerErrorException(OpeNGSyncServerException):
    @property
    def response(self) -> DBEnum:
        return HTTPResponse.INTERNAL_SERVER_ERROR
    
    
class WorkflowException(OpeNGSyncServerException):
    @property
    def response(self) -> DBEnum:
        return HTTPResponse.INTERNAL_SERVER_ERROR