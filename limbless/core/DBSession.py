from typing import Optional

from .DBHandler import DBHandler

class DBSession():
    def __init__(self, db_handler: DBHandler, commit: Optional[bool] = False):
        self.db_handler = db_handler
        self.commit = commit

    def __enter__(self):
        self.db_handler.open_session()
        return self.db_handler

    def __exit__(self, *_):
        self.db_handler.close_session(commit=self.commit)