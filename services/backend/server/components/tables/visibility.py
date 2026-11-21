"""Which related objects a viewer may see in a table's entity filters (options and applied ids).

Insiders see everything. Other users see:

- users: themselves and the members of their groups (the people whose requests, samples and libraries
  are shared with them through a group)
- groups: the groups they are a member of
- requests, projects, pools, samples, libraries, media files: what the model's ``access_level`` grants READ
- anything else (experiments, lab preps, sequencers, ...): nothing, those are insider objects
"""
import sqlalchemy as sa
from sqlalchemy.orm import aliased

from opengsync_db import models, queries as Q, categories as C

_ACCESS_LEVEL = {
    models.SeqRequest: Q.seq_request.access_level,
    models.Project: Q.project.access_level,
    models.Pool: Q.pool.access_level,
    models.Sample: Q.sample.access_level,
    models.Library: Q.library.access_level,
    models.MediaFile: Q.media_file.access_level,
}


def offered(model: type, user: models.User) -> bool:
    """Whether ``user`` may filter by ``model`` at all (customers never see insider-only objects)."""
    return bool(user.is_insider) or model in (models.User, models.Group) or model in _ACCESS_LEVEL


def visible(model: type, user: models.User) -> sa.ColumnElement[bool] | None:
    """WHERE clause limiting ``model`` to what ``user`` may see; ``None`` means no restriction."""
    if user.is_insider:
        return None

    if model is models.User:
        mine = aliased(models.links.UserAffiliation)
        theirs = aliased(models.links.UserAffiliation)
        shares_group = sa.exists(
            sa.select(1).select_from(mine).join(theirs, theirs.group_id == mine.group_id)
            .where(mine.user_id == user.id, theirs.user_id == models.User.id)
        )
        return sa.or_(models.User.id == user.id, shares_group)

    if model is models.Group:
        return sa.exists(
            sa.select(1).where(
                models.links.UserAffiliation.user_id == user.id,
                models.links.UserAffiliation.group_id == models.Group.id,
            )
        )

    if (access_level := _ACCESS_LEVEL.get(model)) is not None:
        return access_level(user.id) >= C.AccessLevel.READ

    return sa.false()
