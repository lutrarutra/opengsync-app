import asyncio
import yaml
from pydantic import BaseModel

from server.core import config, secrets

from opengsync_db import SyncSession, AsyncDBHandler


class CodeFlowerConfig(BaseModel):
    personalization: dict[str, str]


def dev_seed(session: SyncSession):
    from sqlalchemy import orm

def init_db():
    print("Initializing Database and default data...")

    with open("/app/opengsync.yaml", "r") as f:
        config_data = yaml.safe_load(f)

    cf_config = CodeFlowerConfig.model_validate(config_data)

    db = AsyncDBHandler()
    
    db.connect(
        user=config.settings.POSTGRES_USER,
        password=config.settings.POSTGRES_PASSWORD,
        host=config.settings.POSTGRES_HOST,
        db=config.settings.POSTGRES_DB,
        port=config.settings.POSTGRES_PORT
    )
    
    if db._engine is None:
        raise Exception("DB connection could not be established")

    with db.get_session() as session:
        if config.settings.ENVIRONMENT == "dev":
            dev_seed(session)
            
        session.commit()

    db.close()
    db._engine.dispose()
    print("Database initialization complete.")

if __name__ == "__main__":
    asyncio.run(init_db())