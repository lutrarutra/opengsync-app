import os
from dataclasses import dataclass, field

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q

from ...core import dependencies, responses, config, audit_reader, affiliation_values as av, exceptions as exc, redis as rds
from ...core.context import ctx
from ...chat import usage as chat_usage
from ...components.tables import Table, TableState, Col, Text, Variant, related
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


ST = models.ShareToken


class ShareTokenAdminTable(Table):
    key = "ashare"
    model = models.ShareToken
    noun = "share links"
    default_sort = ("created_utc", "desc")
    load = (orm.selectinload(ST.owner), orm.selectinload(ST.paths))
    columns = [
        Col("uuid", "Token", search=Text(ST.uuid), hideable=False, size=1),
        Col("status", "Status", size=1),
        Col(
            "owner", "Created by", sort=related(ST.owner, Q.search.full_name(models.User)), size=2,
            search=Text(Q.search.full_name(models.User), models.User.email, via=ST.owner),
        ),
        Col("created_utc", "Created", sort=True, size=1),
        Col("expiration", "Expires", sort=True, size=1),
        Col("project", "Project", size=2),
        Col("paths", "Paths", size=2),
        Col("size", "Size", size=1),
    ]
    variants = {
        "default": Variant(
            ["uuid", "status", "owner", "created_utc", "expiration", "project", "paths", "size"],
            "components/tables/rows/admin-share-token.html", dom_id="admin-share_token-table", actions=True,
        ),
    }

    def __init__(self, *args, fs_index_session: SyncSession | None = None, session: SyncSession | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.fs_index_session = fs_index_session

    def row_context(self, tokens) -> dict:
        """Projects released with and sizes of the page's tokens (for share-token-row.html)."""
        assert self.session is not None
        return _row_context(self.session, self.fs_index_session, list(tokens))

    tie_break = (ST.uuid.asc(),)  # the primary key is the uuid


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
    state: TableState = Depends(ShareTokenAdminTable.params),
    current_user: models.User = Depends(dependencies.require_admin),
    session: SyncSession = Depends(dependencies.db_session),
    fs_index_session: SyncSession | None = Depends(dependencies.fs_index_session),
):
    table = ShareTokenAdminTable(
        state, route="admin_share_token_table", user=current_user, session=session, fs_index_session=fs_index_session,
    )
    return table.render(session, Q.share_token.select())


@router.post("/share-tokens/{uuid}/expire", name="admin_expire_share_token")
def expire_share_token(
    uuid: str,
    session: SyncSession = Depends(dependencies.db_session),
    fs_index_session: SyncSession | None = Depends(dependencies.fs_index_session),
    redis: rds.RedisClient = Depends(dependencies.redis),
):
    share_token = _get_share_token(session, uuid)
    if share_token.is_expired:
        raise exc.BadRequestException("Share link has already expired.")
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


class AffiliationValueTable(Table):
    """Institutes, departments or PIs as stored on users (core/affiliation_values.py): grouped values, not
    rows of a model, so ``render`` pages them with ``av.listing`` instead of a statement. The search box searches
    the name (PIs: the email with scope Email or a term containing @)."""
    model = models.User  # not used: the rows come from av.listing
    model_backed = False
    key = "aaff"  # per tab: aaff_<kind>, set in __init__
    noun = "values"
    default_sort = ("num_users", "desc")
    columns = [
        Col("name", "Name", sort=True, search=Text(sa.column("name")), hideable=False, size=4),
        Col("email", "Email", search=Text(sa.column("email")), size=3),
        Col("institute", "Institute", size=3),
        Col("num_users", "Users", sort=True, size=1),
        Col("actions", "", hideable=False, size=1),
    ]
    _rows = "components/tables/rows/admin-affiliation-values.html"
    variants = {
        "institute": Variant(["name", "num_users", "actions"], _rows, fields=["name"]),
        "department": Variant(["name", "institute", "num_users", "actions"], _rows, fields=["name"]),
        "pi": Variant(["name", "email", "num_users", "actions"], _rows, fields=["name", "email"]),
    }

    def __init__(self, state: TableState, *, kind: av.Kind, user: models.User):
        super().__init__(state, route="admin_affiliation_value_table", user=user, variant=kind.value)
        self.kind = kind
        self.key = f"aaff_{kind.value}"
        self.dom_id_override = f"admin-affiliations-{kind.value}-table"
        self.url_params["kind"] = kind.value

    def render_values(self, session: SyncSession):
        q = self.state.q
        by_email = self.kind == av.Kind.PI and (self.state.scope == "email" or "@" in q)
        sort, direction = self.state.order_by or self.default_sort
        search = dict(name=None if by_email else (q or None), email=q if by_email else None)

        values, self.total = av.listing(session, self.kind, sort=sort, descending=direction == "desc",
                                        page=self.state.page - 1, limit=self.state.limit, **search)
        self.num_pages = max(1, -(-self.total // self.state.limit))
        self.page = min(self.state.page, self.num_pages)
        if self.page != self.state.page:
            values, self.total = av.listing(session, self.kind, sort=sort, descending=direction == "desc",
                                            page=self.page - 1, limit=self.state.limit, **search)
        if self.total == 0 and q:
            self.unfiltered_total = av.listing(session, self.kind, limit=1)[1]
        self.rows = values
        return responses.htmx_response(
            template=self.template, table=self, rows=values, kind=self.kind,
            pi_accounts=av.pi_accounts(session, values) if self.kind == av.Kind.PI else {},
        )


@router.get("/affiliations", name="admin_affiliation_value_table")
def get_affiliation_value_table(
    kind: av.Kind = Query(..., description="institute, department or pi"),
    state: TableState = Depends(AffiliationValueTable.params),
    current_user: models.User = Depends(dependencies.require_admin),
    session: SyncSession = Depends(dependencies.db_session),
):
    return AffiliationValueTable(state, kind=kind, user=current_user).render_values(session)


# The guard is also declared on the form routers, so that it is on their routes' own dependencies
router.include_router(forms.models.AffiliationValueForm.Router(dependencies=[Depends(dependencies.require_admin)]))
router.include_router(forms.actions.MergeAffiliationValuesAction.Router(dependencies=[Depends(dependencies.require_admin)]))
