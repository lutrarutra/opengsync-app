from typing import Optional, Union
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine
import sqlalchemy as sa

from .AsyncSession import AsyncSession

class AsyncDBHandler:
    session_factory: async_sessionmaker[AsyncSession]
    
    def __init__(
        self,
        expire_on_commit: bool = False, auto_open: bool = False,
        auto_commit: bool = False,
    ):
        self._engine: Optional[AsyncEngine] = None
        self.expire_on_commit = expire_on_commit
        self.auto_open = auto_open
        self.auto_commit = auto_commit

    async def connect(
        self, user: str, password: str, host: str, db: str = "token_db", port: Union[str, int] = 5432
    ) -> None:
        self._url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
        self.public_url = f"postgresql+psycopg://{host}:{port}/{db}"
        
        self._engine = create_async_engine(
            self._url, pool_pre_ping=True,
        )

        try:
            async with self._engine.connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
        except Exception as e:
            raise Exception(f"Could not connect to DB '{self.public_url}':\n{e}")
            
        self.session_factory = async_sessionmaker(
            bind=self._engine, 
            expire_on_commit=self.expire_on_commit,
            class_=AsyncSession
        )

    def get_session(self) -> AsyncSession:
        """Returns a new async session."""
        return self.session_factory()

    async def close(self) -> None:
        """Dispose the engine pool."""
        if self._engine:
            await self._engine.dispose()