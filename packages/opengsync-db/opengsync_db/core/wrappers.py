from typing import Callable, Any, TypeVar

from functools import wraps

F = TypeVar("F", bound=Callable[..., Any])


def db_transaction(auto_open: bool) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        if auto_open:
            @wraps(func)
            def wrapper(self, *args, **kwargs):
                if not (persist_session := self._session is not None):
                    self.open_session()

                result = func(self, *args, **kwargs)

                if not persist_session:
                    self.close_session()
                
                return result
            return wrapper  # type: ignore
        else:
            return func
    return decorator