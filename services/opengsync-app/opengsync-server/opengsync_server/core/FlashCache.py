import redis


class FlashCache:
    def __init__(self):
        self.r: redis.StrictRedis

    def connect(self, host: str, port: int, db: int):
        self.r = redis.StrictRedis(host=host, port=port, db=db)
        self.r.flushdb()

    def get(self, sid: str, category: str | list[str] | None = None) -> list[tuple[str, str]]:
        if isinstance(category, str):
            category = [category]

        flashes = []
        if category is None:
            all_flashes: dict[bytes, bytes] = self.r.hgetall(sid)  # type: ignore
            for cat, messages in all_flashes.items():
                cat = cat.decode()
                if messages:
                    flashes.extend((cat, msg) for msg in messages.decode().split(','))
        else:
            for cat in category:
                messages: bytes | None = self.r.hget(sid, cat)  # type: ignore
                if messages:
                    flashes.extend((cat, msg) for msg in messages.decode().split(','))

        return flashes
    
    def add(self, sid: str, flashes: list[tuple[str, str]]):
        flashes = self.get(sid) + flashes

        self.r.delete(sid)
        
        self.r.hset(sid, mapping={
            "info": ",".join(msg for cat, msg in flashes if cat in ["info", "message"]),
            "success": ",".join(msg for cat, msg in flashes if cat == "success"),
            "warning": ",".join(msg for cat, msg in flashes if cat == "warning"),
            "error": ",".join(msg for cat, msg in flashes if cat in ["error", "danger"])
        })

    def consume(self, sid: str | None, category: str | list[str] | None = None) -> list[tuple[str, str]]:
        if sid is None:
            return []
        flashes = self.get(sid, category)

        if category is not None:
            if isinstance(category, str):
                category = [category]
            for cat in category:
                self.r.hdel(sid, cat)

        return flashes
    
    def consume_all(self, sid: str | None) -> dict[str, list[str]]:
        if sid is None:
            return {}
        flashes = self.get(sid)
        self.r.delete(sid)
        categorized_flashes = {}
        for cat, msg in flashes:
            if cat not in categorized_flashes:
                categorized_flashes[cat] = []
            categorized_flashes[cat].append(msg)
        return categorized_flashes