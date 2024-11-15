from typing import Any

import pandas as pd
import pickle

import redis


class RedisConfigFileCache():
    def connect(self, host: str, port: int, db: int):
        self.r = redis.StrictRedis(host=host, port=port, db=db, decode_responses=False)

    def get(self, key: str) -> tuple[dict[str, Any], dict[str, pd.DataFrame]] | None:
        if (serialized_data := self.r.get(key)) is None:
            return None
        
        data = pickle.loads(serialized_data)  # type: ignore
        metadata = data.pop("metadata")
        return metadata, data
    
    def set(self, key: str, metadata: dict[str, Any], data: dict[str, pd.DataFrame]):
        serialized_data = pickle.dumps({"metadata": metadata, **data})
        self.r.set(key, serialized_data)
