"""Deactivating a user must also drop the app's cached user and access levels (they log out right away)."""
import fnmatch


class _FakeRedis:
    def __init__(self, keys: list[str]):
        self.keys = set(keys)

    def delete(self, *keys):
        self.keys -= set(keys)

    def scan_iter(self, match: str, count: int = 0):
        return [k for k in list(self.keys) if fnmatch.fnmatchcase(k, match)]


def test_forget_cached_users_drops_only_their_keys(import_worker_task):
    module = import_worker_task("deactivate_inactive_users")
    redis = _FakeRedis([
        "user:7", "user:70", "access:seq_request:1:user:7", "access:project:3:user:7",
        "access:seq_request:1:user:70", "access:user:7:user:8",
    ])

    module.forget_cached_users(redis, [7])

    assert redis.keys == {"user:70", "access:seq_request:1:user:70", "access:user:7:user:8"}
