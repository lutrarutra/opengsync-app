import datetime as dt

from opengsync_db import categories as C, SyncDBHandler, queries as Q

from . import logger

# Admins are never auto-deactivated, so someone is always left to reactivate accounts.
DEACTIVATABLE_ROLES = [
    C.UserRole.BIOINFORMATICIAN,
    C.UserRole.TECHNICIAN,
    C.UserRole.CLIENT,
    C.UserRole.TEMPORARY,
]


def deactivate_inactive_users(db: SyncDBHandler, inactivity_days: int) -> list[int]:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=inactivity_days)
    logger.info(f"Deactivating users who have not logged in since {cutoff.isoformat()}")

    deactivated: list[int] = []
    for user in db.session.get_all(Q.user.select(
        role_in=DEACTIVATABLE_ROLES,
        last_login_before=cutoff,
    ), limit=None):
        logger.info(f"Deactivating user {user.id} ({user.email}), role {user.role.label}, last login {user.last_login}")
        user.role = C.UserRole.DEACTIVATED
        db.session.save(user)
        deactivated.append(user.id)
    return deactivated


def forget_cached_users(redis, user_ids: list[int]) -> None:
    """Drop the app's cached user and access levels, so a deactivated user is logged out right away."""
    for user_id in user_ids:
        redis.delete(f"user:{user_id}")
        for key in redis.scan_iter(match=f"access:*:user:{user_id}", count=500):
            redis.delete(key)
