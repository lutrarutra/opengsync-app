import redis

class FlashCache:
    PRIORITY = ["error", "warning", "info", "success"]

    def __init__(self, time_to_live_hours: int = 1):
        self.r: redis.StrictRedis = None  # type: ignore
        self.time_to_live_hours = time_to_live_hours

    def connect(self, host: str, port: int, db: int):
        self.r = redis.StrictRedis(host=host, port=port, db=db, decode_responses=True)
        self.r.flushdb()

    def _redis_key(self, sid: str, category: str) -> str:
        return f"{sid}:{category}"

    def add(self, sid: str, flashes: list[tuple[str, str]]):
        for cat, msg in flashes:
            cat = self._normalize_category(cat)
            self.r.rpush(self._redis_key(sid, cat), msg)
            self.r.expire(self._redis_key(sid, cat), self.time_to_live_hours * 3600)
            
    def get(self, sid: str, category: str | list[str] | None = None) -> list[tuple[str, str]]:
        categories = self._categories(category)
        result = []
        for cat in categories:
            msgs: list = self.r.lrange(self._redis_key(sid, cat), 0, -1)  # type: ignore
            result.extend((cat, msg) for msg in msgs)
        return result

    def consume(self, sid: str, category: str | list[str] | None = None) -> list[tuple[str, str]]:
        categories = self._categories(category)
        consumed = []
        for cat in categories:
            msgs: list = self.r.lrange(self._redis_key(sid, cat), 0, -1)  # type: ignore
            if msgs:
                self.r.delete(self._redis_key(sid, cat))
                consumed.extend((cat, msg) for msg in msgs)
        return consumed

    def consume_one(self, sid: str, category: str | None = None) -> tuple[str, str] | None:
        cats = self._categories(category, priority=True)
        for cat in cats:
            key = self._redis_key(sid, cat)
            msg: str | None = self.r.lpop(key)  # type: ignore
            if msg is not None:
                return (cat, msg)
        return None

    def consume_all(self, sid: str) -> list[dict] | None:
        result = []
        for cat in self.PRIORITY:
            key = self._redis_key(sid, cat)
            msgs: list[str] = self.r.lrange(key, 0, -1)  # type: ignore
            if msgs:
                self.r.delete(key)
                result.extend({"category": cat, "message": msg} for msg in msgs)
        return result

    def _normalize_category(self, cat: str) -> str:
        mapping = {
            "danger": "error",
            "message": "info",
        }
        return mapping.get(cat, cat)

    def _categories(self, category, priority=False):
        if category is None:
            return self.PRIORITY if priority else self.PRIORITY[::-1]  # Use normal or reverse order
        elif isinstance(category, str):
            return [self._normalize_category(category)]
        else:
            return [self._normalize_category(cat) for cat in category]