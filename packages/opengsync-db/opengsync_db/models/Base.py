from typing import Union

from sqlalchemy import orm
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    def _is_async_context(self) -> bool:
        """Check if this instance is bound to an async session.
        
        orm.object_session() returns the internal sync wrapper, so
        isinstance(session, AsyncSession) doesn't work. Instead we check
        a tag that AsyncSession.__init__ sets on its sync_session.
        """
        session = orm.object_session(self)
        if session is None:
            return False
        return getattr(session, "_is_async_context", False)

    def show_value(self) -> bool:
        return False
    
    def name_class(self) -> str:
        return ""
    
    def description_class(self) -> str:
        return ""
    
    def to_str(self) -> str:
        res = self.search_name()
        if self.show_value():
            res += f" [{self.search_value()}]"
        if self.search_description():
            res += f" ({self.search_description()})"

        return res

    def search_value(self) -> Union[int, str]:
        raise NotImplementedError()
    
    def search_name(self) -> str:
        raise NotImplementedError()
    
    def search_description(self) -> str | None:
        return None