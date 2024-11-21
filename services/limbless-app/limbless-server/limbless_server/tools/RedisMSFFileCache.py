from typing import Any, TYPE_CHECKING

import pickle

import redis

from .. import logger

if TYPE_CHECKING:
    from ..forms.MultiStepForm import StepFile


class RedisMSFFileCache():
    def connect(self, host: str, port: int, db: int):
        self.r = redis.StrictRedis(host=host, port=port, db=db, decode_responses=False)

    def get(self, key: str) -> tuple[dict[str, Any], dict[str, "StepFile"]] | None:
        if (serialized_data := self.r.get(key)) is None:
            return None
        
        logger.debug(f"Fetching from cache: {key}")

        data = pickle.loads(serialized_data)  # type: ignore
        header = data.pop("header")
        return header, data
    
    def set(self, key: str, header: dict[str, Any], steps: dict[str, "StepFile"]) -> None:
        self.r.set(key, pickle.dumps({"header": header, **steps}))

    def delete(self, key: str) -> None:
        self.r.delete(key)
