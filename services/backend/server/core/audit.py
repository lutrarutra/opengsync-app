from fastapi import Request
from fastapi.routing import APIRoute

class AuditLogger:
    def __init__(self, request: Request):
        route: APIRoute | None = request.scope.get("route")
        self.route = route.path if route else request.url.path
        self.method = request.method.upper()
        
        self.resource_id: str | None = None
        self.metadata: dict = {}

        request.state.audit = self