import os
from dataclasses import dataclass, field

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, utils

from ...core import dependencies, responses, config, audit_reader, affiliation_values as av, exceptions as exc, redis as rds
from ...core.context import ctx
from ...chat import usage as chat_usage
from ...components.tables import HTMXTable, TableCol
from ... import forms
from ...forms.common import SelectedPathsMixin
from ...utils import fs_index, share_fs_cache
from ...utils.file_browser import MAX_SELECTED_PATHS, resolve_share_path
from .data_browser import picker_changes

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(dependencies.require_admin)])

CHAT_USAGE_DAYS = (7, 30, 90)


@router.get("/chat-usage", name="admin_chat_usage")
def get_chat_usage(
    days: int = Query(30),
    session: SyncSession = Depends(dependencies.db_session),
):
    if days not in CHAT_USAGE_DAYS:
        raise exc.BadRequestException(f"days must be one of {', '.join(map(str, CHAT_USAGE_DAYS))}.")

    audit_folder = os.path.join(config.settings.app_config.log_folder, "audits")
    summary = chat_usage.summarize(audit_folder, now=config.settings.now(), days=days)

    user_ids = {u.user_id for u in summary.top_users} | {m.user_id for m in summary.recent}
    user_ids.discard(None)
    users = {
        user.id: user for user in session.get_all(sa.select(models.User).where(models.User.id.in_(user_ids)), limit=None)
    } if user_ids else {}

    return responses.htmx_response(
        template="components/admin/chat-usage.html",
        usage=summary, users=users, day_options=CHAT_USAGE_DAYS,
        chat_enabled=config.settings.app_config.chat.enabled,
    )


@router.get("/audits", name="admin_audit_log")
def get_audit_log(
    request: Request,
    page: int = Query(0, ge=0),
    session: SyncSession = Depends(dependencies.db_session),
):
    try:
        flt = audit_reader.parse_filter(dict(request.query_params), today=config.settings.now().date())
    except ValueError as e:
        raise exc.BadRequestException(str(e))
    audit_folder = os.path.join(config.settings.app_config.log_folder, "audits")
    result = audit_reader.query(audit_folder, flt, tz=config.settings.TIMEZONE, page=page)

    user_ids = {e.user_id for e in result.entries} | {e.owner_id for e in result.entries}
    if flt.user_id is not None:
        user_ids.add(flt.user_id)
    user_ids.discard(None)
    users = {
        user.id: user for user in session.get_all(sa.select(models.User).where(models.User.id.in_(user_ids)), limit=None)
    } if user_ids else {}

    filters = {k: v for k, v in request.query_params.items() if k in audit_reader.FILTERS and v.strip()}
    return responses.htmx_response(
        template="components/admin/audit-log.html",
        result=result, flt=flt, filters=filters, users=users,
    )


class ShareTokenAdminTable(HTMXTable):
    columns = [
        TableCol(title="Token", label="uuid", col_size=1, searchable=True),
        TableCol(title="Status", label="status", col_size=1),
        TableCol(title="Created by", label="owner", col_size=2, searchable=True, sortable=True, sort_by="owner_id"),
        TableCol(title="Created", label="created_utc", col_size=1, sortable=True),
        TableCol(title="Expires", label="expiration", col_size=1),
        TableCol(title="Project", label="project", col_size=2),
        TableCol(title="Paths", label="paths", col_size=2),
        TableCol(title="Size", label="size", col_size=1),
    ]


@dataclass
class ShareSize:
    # None: not in the fs-index
    paths: dict[str, int | None] = field(default_factory=dict)
    total: int = 0
    # some path is not in the index, so the total is a lower bound
    partial: bool = False


def _share_sizes(tokens: list[models.ShareToken], fs_index_session: SyncSession | None) -> dict[str, ShareSize] | None:
    """Sizes from the fs-index, None when it is disabled or not built. A path inside another path of the same
    token is listed with its size but not counted twice in the total."""
    if fs_index_session is None:
        return None
    sizes = fs_index.path_sizes(fs_index_session, [p.path for token in tokens for p in token.paths])
    result: dict[str, ShareSize] = {}
    for token in tokens:
        share = ShareSize(paths={p.path: sizes.get(p.path) for p in token.paths})
        for path in SelectedPathsMixin.collapse_paths(share.paths):
            if (size := share.paths[path]) is None:
                share.partial = True
            else:
                share.total += size
        result[token.uuid] = share
    return result


def _row_context(session: SyncSession, fs_index_session: SyncSession | None, tokens: list[models.ShareToken]) -> dict:
    """What share-token-row.html needs besides the token: the projects released with it and the sizes."""
    projects: dict[str, list[models.Project]] = {}
    if uuids := [token.uuid for token in tokens]:
        for project in session.get_all(sa.select(models.Project).where(models.Project.share_token_uuid.in_(uuids)), limit=None):
            projects.setdefault(project.share_token_uuid, []).append(project)  # type: ignore[arg-type]
    return {"projects": projects, "sizes": _share_sizes(tokens, fs_index_session)}


def _get_share_token(session: SyncSession, uuid: str) -> models.ShareToken:
    return session.get_one(Q.share_token.select(uuid=uuid), options=[
        orm.selectinload(models.ShareToken.owner),
        orm.selectinload(models.ShareToken.paths),
    ])


@router.get("/share-tokens", name="admin_share_token_table")
def get_share_token_table(
    page: int = Query(0, ge=0),
    uuid: str | None = Query(None, description="Search by share token UUID prefix"),
    owner: str | None = Query(None, description="Search by owner name"),
    order_by: utils.OrderBy | None = Depends(dependencies.parse_order_by(model=models.ShareToken, default=models.ShareToken.created_utc.desc())),
    session: SyncSession = Depends(dependencies.db_session),
    fs_index_session: SyncSession | None = Depends(dependencies.fs_index_session),
):
    table = ShareTokenAdminTable(route="admin_share_token_table", page=page, order_by=order_by)

    stmt = Q.share_token.select()
    if uuid:
        table.active_search_var = "uuid"
        table.active_query_value = uuid
        stmt = Q.share_token.search(uuid=uuid, statement=stmt)
    elif owner:
        table.active_search_var = "owner"
        table.active_query_value = owner
        stmt = Q.share_token.search(owner_name=owner, statement=stmt)

    share_tokens = list(table.paginate(
        session, stmt, page=page, order_by=order_by,
        options=[orm.selectinload(models.ShareToken.owner), orm.selectinload(models.ShareToken.paths)],
    ))

    return responses.htmx_response(
        template="components/admin/share-tokens.html",
        share_tokens=share_tokens, table=table,
        **_row_context(session, fs_index_session, share_tokens),
    )


@router.post("/share-tokens/{uuid}/expire", name="admin_expire_share_token")
def expire_share_token(
    uuid: str,
    session: SyncSession = Depends(dependencies.db_session),
    fs_index_session: SyncSession | None = Depends(dependencies.fs_index_session),
    redis: rds.RedisClient = Depends(dependencies.redis),
):
    share_token = _get_share_token(session, uuid)
    share_token._expired = True
    session.save(share_token)
    # the share routes cache the token, so without this the link would keep working for a while
    share_fs_cache.invalidate(redis, share_token.uuid)

    return responses.htmx_response(
        template="components/admin/share-token-row.html",
        share_token=share_token,
        flash=responses.flash("Share link expired.", "success"),
        **_row_context(session, fs_index_session, [share_token]),
    )


@router.get("/share-tokens/{uuid}/paths", name="admin_share_token_picker")
def share_token_picker(
    uuid: str,
    session: SyncSession = Depends(dependencies.db_session),
):
    """The share's paths ticked in the whole-share browser (the Data tab's "Manage data" picker)."""
    share_token = _get_share_token(session, uuid)
    return responses.htmx_response(
        template="components/file-browser/data-picker.html",
        data_owner_label="share link",
        data_owner_name=f"{share_token.uuid[:8]}… by {share_token.owner.name}",
        existing_paths=sorted(p.path for p in share_token.paths),
        submit_url=ctx.request.url_for("admin_save_share_token_paths", uuid=share_token.uuid),
        max_selected_paths=MAX_SELECTED_PATHS,
    )


@router.post("/share-tokens/{uuid}/paths", name="admin_save_share_token_paths")
def save_share_token_paths(
    request: Request,
    uuid: str,
    session: SyncSession = Depends(dependencies.db_session),
    redis: rds.RedisClient = Depends(dependencies.redis),
):
    """The picker's changes, checked as when a share is created (SharePathAction): one bad path rejects them all."""
    share_token = _get_share_token(session, uuid)
    add, remove = picker_changes(request)

    share_root = config.settings.app_config.share_root
    resolved: list[str] = []
    invalid: list[str] = []
    for path in add:
        try:
            resolved.append(resolve_share_path(share_root, path))
        except ValueError as e:
            invalid.append(f"{path}: {e}")
    if invalid:
        raise exc.BadRequestException(f"{'; '.join(invalid[:3])}{' …' if len(invalid) > 3 else ''}")

    existing = {p.path for p in share_token.paths}
    # a ticked folder replaces the paths inside it
    paths = set(SelectedPathsMixin.collapse_paths([*(existing - set(remove)), *resolved]))
    if not paths:
        raise exc.BadRequestException("A share link needs at least one path: expire it instead.")

    for share_path in [p for p in share_token.paths if p.path not in paths]:
        share_token.paths.remove(share_path)
    for path in sorted(paths - existing):
        share_token.paths.append(models.SharePath(path=path))
    session.save(share_token)
    share_fs_cache.invalidate(redis, share_token.uuid)

    added, removed = len(paths - existing), len(existing - paths)
    changes = [f"{n} path{'s' if n > 1 else ''} {verb}" for n, verb in ((added, "added"), (removed, "removed")) if n]
    if changes:
        flash = responses.flash(f"{' and '.join(changes)}.", "success")
    else:
        flash = responses.flash("Nothing changed: the share link already has these paths.", "info")
    return responses.htmx_response(redirect=ctx.request.url_for("admin_shares_page"), flash=flash)


class AffiliationValueTable(HTMXTable):
    columns = [
        TableCol(title="Name", label="name", col_size=4, searchable=True, sortable=True),
        TableCol(title="Email", label="email", col_size=3, searchable=True),
        TableCol(title="Institute", label="institute", col_size=3),
        TableCol(title="Users", label="num_users", col_size=1, sortable=True),
        TableCol(title="", label="actions", col_size=1),
    ]


@router.get("/affiliations", name="admin_affiliation_value_table")
def get_affiliation_value_table(
    kind: av.Kind = Query(..., description="institute, department or pi"),
    page: int = Query(0, ge=0),
    name: str | None = Query(None, description="Search by name"),
    email: str | None = Query(None, description="Search PIs by email"),
    order_by: str | None = Query(None, description="'name' or 'num_users' and direction, e.g. 'name:asc'"),
    session: SyncSession = Depends(dependencies.db_session),
):
    sort, _, direction = (order_by or "num_users:desc").partition(":")
    if sort not in av.SORT_COLUMNS or direction not in ("asc", "desc"):
        raise exc.BadRequestException("order_by must be 'name' or 'num_users' with ':asc' or ':desc'.")
    order = sa.column(sort)
    table = AffiliationValueTable(
        route="admin_affiliation_value_table", page=page, order_by=order.desc() if direction == "desc" else order.asc(),
    )
    table.url_params["kind"] = kind.value

    if name:
        table.active_search_var, table.active_query_value = "name", name
    elif email and kind == av.Kind.PI:
        table.active_search_var, table.active_query_value = "email", email

    values, count = av.listing(
        session, kind, name=name, email=None if name else email,
        sort=sort, descending=direction == "desc", page=page, limit=table.limit,
    )
    table.set_num_pages(count)

    return responses.htmx_response(
        template="components/admin/affiliation-values.html",
        table=table, kind=kind, values=values,
        pi_accounts=av.pi_accounts(session, values) if kind == av.Kind.PI else {},
    )


# The guard is also declared on the form routers, so that it is on their routes' own dependencies
router.include_router(forms.models.AffiliationValueForm.Router(dependencies=[Depends(dependencies.require_admin)]))
router.include_router(forms.actions.MergeAffiliationValuesAction.Router(dependencies=[Depends(dependencies.require_admin)]))
