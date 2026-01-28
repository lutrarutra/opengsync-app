import io
import json
import pyarrow as pa
from pyarrow import parquet as pq
import pandas as pd
import redis


class RedisMSFFileCache():
    def __init__(self):
        self.r: redis.StrictRedis | None = None

    def connect(self, host: str, port: int, db: int):
        self.r = redis.StrictRedis(host=host, port=port, db=db, decode_responses=False)

    def get_table(self, key: str) -> pd.DataFrame | None:
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        
        if (data := self.r.get(key)) is None:
            return None
        
        return pd.read_parquet(io.BytesIO(data))  # type: ignore
    
    def get_tables(self, pattern: str) -> dict[str, pd.DataFrame]:
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        
        tables = {}
        for key in self.r.scan_iter(match=pattern):
            if (data := self.r.get(key)) is not None:
                tables[key.decode('utf-8')] = pd.read_parquet(io.BytesIO(data))  # type: ignore
        
        return tables

    def get_dicts(self, pattern: str) -> dict[str, dict]:
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        
        dicts = {}
        for key in self.r.scan_iter(match=pattern):
            if (data := self.r.get(key)) is not None:
                dicts[key.decode('utf-8')] = json.loads(data.decode('utf-8'))  # type: ignore
        
        return dicts 
    
    def get_dict(self, key: str) -> dict | None:
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        
        if (data := self.r.get(key)) is None:
            return None
        
        return json.loads(data.decode('utf-8'))  # type: ignore

    def set_table(self, key: str, table: pd.DataFrame) -> None:
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        
        buffer = io.BytesIO()
        pq.write_table(pa.Table.from_pandas(table), buffer)
        self.r.set(key, buffer.getvalue())

    def set_dict(self, key: str, data: dict) -> None:
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        
        self.r.set(key, json.dumps(data).encode('utf-8'))

    def delete(self, key: str) -> None:
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        self.r.delete(key)

    def delete_pattern(self, pattern: str) -> None:
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        
        for key in self.r.scan_iter(match=pattern):
            self.r.delete(key)

    def get_steps(self, key: str) -> list[str]:
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        
        if (data := self.r.get(key)) is None:
            return []
        
        return json.loads(data.decode('utf-8'))  # type: ignore

    def set_steps(self, key: str, steps: list[str]) -> None:
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        
        self.r.set(key, json.dumps(steps).encode('utf-8'))

