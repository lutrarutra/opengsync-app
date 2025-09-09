from .ExtendedEnum import DBEnum, ExtendedEnum


class HTTPResponse(ExtendedEnum[DBEnum], enum_type=DBEnum):
    OK = DBEnum(200, "OK")
    BAD_REQUEST = DBEnum(400, "Bad Request")
    UNAUTHORIZED = DBEnum(401, "Unauthorized")
    FORBIDDEN = DBEnum(403, "Forbidden")
    NOT_FOUND = DBEnum(404, "Not Found")
    METHOD_NOT_ALLOWED = DBEnum(405, "Method Not Allowed")
    TOO_MANY_REQUESTS = DBEnum(429, "Too Many Requests")
    INTERNAL_SERVER_ERROR = DBEnum(500, "Internal Server Error")