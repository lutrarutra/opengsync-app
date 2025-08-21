from typing import Callable, TypeVar, Any, TYPE_CHECKING
from functools import wraps

F = TypeVar('F', bound=Callable[..., Any])

if TYPE_CHECKING:
    from .DBHandler import DBHandler


class DBBlueprint:
    def __init__(self, name: str, db: "DBHandler") -> None:
        self.name = name
        self.db = db
        self._register_transactions()

    def _register_transactions(self) -> None:
        """Automatically wraps all methods marked with @transaction."""
        for name, method in self.__class__.__dict__.items():
            if callable(method) and hasattr(method, "_is_transaction"):
                wrapped = self._create_wrapped_transaction(method)
                setattr(self, name, wrapped)

    def _create_wrapped_transaction(self, func: F) -> F:
        """Creates a wrapped transaction method with session management."""
        @wraps(func)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if self.db.auto_open:
                persist_session = self.db._session is not None
                if not persist_session:
                    self.db.open_session()

                result = func(self, *args, **kwargs)

                if not persist_session:
                    self.db.close_session()
                return result
            else:
                return func(self, *args, **kwargs)
        return wrapped  # type: ignore[return-value]

    @classmethod
    def transaction(cls, func: F) -> F:
        """Decorator to mark methods as transactions."""
        func._is_transaction = True  # type: ignore
        return func