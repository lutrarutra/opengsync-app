from dataclasses import dataclass
from .ExtendedEnum import DBEnum, ExtendedEnum


@dataclass(eq=False, frozen=True)
class HTTPResponseEnum(DBEnum):
    label: str

class HTTPResponse(ExtendedEnum):
    label: str
    
    OK = HTTPResponseEnum(200, "OK")
    BAD_REQUEST = HTTPResponseEnum(400, "Bad Request")
    UNAUTHORIZED = HTTPResponseEnum(401, "Unauthorized")
    FORBIDDEN = HTTPResponseEnum(403, "Forbidden")
    NOT_FOUND = HTTPResponseEnum(404, "Not Found")
    METHOD_NOT_ALLOWED = HTTPResponseEnum(405, "Method Not Allowed")
    TOO_MANY_REQUESTS = HTTPResponseEnum(429, "Too Many Requests")
    INTERNAL_SERVER_ERROR = HTTPResponseEnum(500, "Internal Server Error")