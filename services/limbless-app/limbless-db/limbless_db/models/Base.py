from typing import Optional, Union

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
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
    
    def search_description(self) -> Optional[str]:
        return None