"""Data tab file browser: a project's, request's, experiment's or library's data paths, browsed live.

`data_browser_router(scope)` adds the same routes to each owner's router, named after it
(e.g. `project_browser_entries`, `serve_seq_request_file`), so their URLs live under the owner:
`/htmx/projects/{project_id}/browse/...`.

Admins and bioinformaticians add and remove data with "Manage data": a full-screen modal with the insider browser over the whole
share (data-picker.html). Linked paths start ticked; the ticked and unticked ones are posted to
`save_<entity>_data_paths`.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from collections.abc import Callable

from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import config, dependencies, responses, exceptions as exc, redis as rds
from ...core.context import ctx
from ...forms.common import SelectedPathsMixin
from ...utils.file_browser import (
    MAX_SELECTED_PATHS, PROJECT_SERVABLE_EXTENSIONS, infer_data_path_type, is_servable, is_share_root, is_within_root,
    servable_mimetype,
)
from ...utils.io import is_browser_friendly
from ...utils.shared_file_browser import SharedFileBrowser
from ...utils import fs_index

DATA_BROWSER_PAGE_LIMIT = 50


def experiment_data_permissions(
    experiment_id: int,
    _: models.User = Depends(dependencies.require_insider),
    session: SyncSession = Depends(dependencies.db_session),
) -> C.AccessLevel:
    """Experiments have no access rules of their own: their data is for insiders."""
    if session.first(Q.experiment.select(id=experiment_id)) is None:
        raise exc.NotFoundException("Experiment not found.")
    return C.AccessLevel.INSIDER


@dataclass(frozen=True)
class DataScope:
    # route name prefix and DataPath foreign key (`<entity>_id`)
    entity: Literal["project", "seq_request", "experiment", "library"]
    # shown in "Remove from <label>" and "No data has been added to this <label> yet."
    label: str
    # checks READ access; declares the `<entity>_id` path parameter
    permissions: Callable[..., C.AccessLevel]
    page_route: str
    tab: str

    @property
    def id_param(self) -> str:
        return f"{self.entity}_id"

    def entity_id(self, request: Request) -> int:
        # validated as an int by `permissions`, which declares it
        return int(request.path_params[self.id_param])

    def owner(self, session: SyncSession, entity_id: int) -> models.Project | models.SeqRequest | models.Experiment | models.Library:
        return session.get_one(getattr(Q, self.entity).select(id=entity_id))

    @staticmethod
    def owner_name(owner: models.Project | models.SeqRequest | models.Experiment | models.Library) -> str:
        if isinstance(owner, models.Project):
            return owner.identifier or owner.title
        return owner.name

    def page_url(self, entity_id: int) -> str:
        return str(ctx.request.url_for(self.page_route, **{self.id_param: entity_id}).include_query_params(tab=self.tab))

    def data_paths(self, session: SyncSession, entity_id: int) -> list[models.DataPath]:
        return list(session.get_all(Q.data_path.select(**{self.id_param: entity_id}), limit=None))

    def browser(self, entity_id: int, data_paths: list[models.DataPath], redis: rds.RedisClient) -> SharedFileBrowser:
        return SharedFileBrowser.for_data_paths(
            Path(config.settings.app_config.share_root),
            f"{self.entity}:{entity_id}",
            [data_path.path for data_path in data_paths],
            redis=redis,
        )


def _subpath(subpath: str) -> Path:
    if not subpath or subpath in (".", "/"):
        return Path()
    return Path(subpath)


def _by_path(data_paths: list[models.DataPath]) -> dict[str, list[models.DataPath]]:
    by_path: dict[str, list[models.DataPath]] = {}
    for data_path in data_paths:
        by_path.setdefault(Path(data_path.path).as_posix(), []).append(data_path)
    return by_path


def data_browser_router(scope: DataScope) -> APIRouter:
    router = APIRouter()
    id_path = "/{" + scope.id_param + "}"

    @router.delete(f"{id_path}/remove-data_path", name=f"remove_{scope.entity}_data_path", dependencies=[Depends(dependencies.require_data_assigner)])
    def remove_data_path(
        request: Request,
        data_path_id: int = Query(..., description="Data path ID to remove"),
        _: C.AccessLevel = Depends(scope.permissions),
        session: SyncSession = Depends(dependencies.db_session),
    ):
        entity_id = scope.entity_id(request)
        data_path = session.get_one(Q.data_path.select(id=data_path_id))
        if getattr(data_path, scope.id_param) != entity_id:
            raise exc.BadRequestException(f"Data path not found in {scope.label}.")

        session.delete(data_path)

        return responses.htmx_response(
            redirect=scope.page_url(entity_id),
            flash=responses.flash("Data path removed.", "success"),
        )

    @router.get(f"{id_path}/manage-data", name=f"{scope.entity}_data_picker")
    def data_picker(
        request: Request,
        _: C.AccessLevel = Depends(scope.permissions),
        __: models.User = Depends(dependencies.require_data_assigner),
        session: SyncSession = Depends(dependencies.db_session),
    ):
        """The whole share in a full-screen modal, to tick paths to link and untick linked ones."""
        entity_id = scope.entity_id(request)
        return responses.htmx_response(
            template="components/file-browser/data-picker.html",
            data_owner_label=scope.label,
            data_owner_name=scope.owner_name(scope.owner(session, entity_id)),
            existing_paths=sorted({Path(data_path.path).as_posix() for data_path in scope.data_paths(session, entity_id)}),
            submit_url=ctx.request.url_for(f"save_{scope.entity}_data_paths", **{scope.id_param: entity_id}),
            max_selected_paths=MAX_SELECTED_PATHS,
        )

    @router.post(f"{id_path}/data_paths", name=f"save_{scope.entity}_data_paths")
    def save_data_paths(
        request: Request,
        _: C.AccessLevel = Depends(scope.permissions),
        __: models.User = Depends(dependencies.require_data_assigner),
        session: SyncSession = Depends(dependencies.db_session),
    ):
        """The picker's changes: share-root relative paths to link (`add-0`, `add-1`, ...) and to unlink (`remove-0`, ...).

        Only what was ticked or unticked is sent, so paths linked meanwhile by someone else stay.
        Indexed fields, as parse_form_data keeps one value per field name.
        """
        entity_id = scope.entity_id(request)
        owner = scope.owner(session, entity_id)
        form = getattr(request.state, "form_data", None) or {}

        def field(prefix: str) -> list[str]:
            return [value for key, value in form.items() if key.startswith(prefix) and isinstance(value, str)]

        add, remove = field("add-"), field("remove-")
        if not add and not remove:
            raise exc.BadRequestException("Nothing to save: tick or untick files and folders first.")
        if len(add) > MAX_SELECTED_PATHS:
            raise exc.BadRequestException(f"At most {MAX_SELECTED_PATHS} paths can be added at once.")

        # every path is checked before anything is saved, so one bad path rejects them all
        share_root = Path(config.settings.app_config.share_root)
        roots = [p for p in add if is_share_root(p) and Path(p).parts and not Path(p).is_absolute()]
        if roots:
            raise exc.BadRequestException(
                f"A whole share folder can't be added ({', '.join(roots[:3])}), only files and folders inside it."
            )
        invalid = [
            p for p in add
            if not Path(p).parts or Path(p).is_absolute() or ".." in Path(p).parts
            or not is_within_root(share_root, p) or not (share_root / p).exists()
        ]
        if invalid:
            raise exc.BadRequestException(f"Not found on the share: {', '.join(invalid[:3])}{' …' if len(invalid) > 3 else ''}")

        # unlinked whether or not they are still on storage; the files stay
        unlink = {Path(p).as_posix() for p in remove}
        removed = 0
        existing: set[str] = set()
        for data_path in scope.data_paths(session, entity_id):
            if Path(data_path.path).as_posix() in unlink:
                session.delete(data_path)
                removed += 1
            else:
                existing.add(Path(data_path.path).as_posix())

        # a ticked folder covers the ticked paths inside it; paths already linked are skipped
        added = 0
        for rel_path in SelectedPathsMixin.collapse_paths(Path(p).as_posix() for p in add):
            if rel_path in existing:
                continue
            session.save(Q.data_path.create(
                path=rel_path, type=infer_data_path_type(share_root / rel_path), **{scope.entity: owner},
            ))
            added += 1

        changes = [f"{n} path{'s' if n > 1 else ''} {verb}" for n, verb in ((added, "added"), (removed, "removed")) if n]
        if changes:
            flash = responses.flash(f"{' and '.join(changes)}.", "success")
        else:
            flash = responses.flash(f"Nothing changed: the {scope.label} already has these paths.", "info")
        return responses.htmx_response(redirect=scope.page_url(entity_id), flash=flash)

    @router.get(f"{id_path}/browse", name=f"{scope.entity}_browser_entries")
    @router.get(f"{id_path}/browse/{{subpath:path}}", name=f"{scope.entity}_browser_entries")
    def browser_entries(
        request: Request,
        subpath: str = "",
        page: int = Query(0, ge=0),
        sort_by: Literal["name", "size", "mtime"] = Query("name"),
        sort_order: Literal["asc", "desc"] | None = Query(None),
        located: bool = Query(False, description="Opened as the current location: render a path bar above the entries"),
        _: C.AccessLevel = Depends(scope.permissions),
        current_user: models.User = Depends(dependencies.require_user),
        session: SyncSession = Depends(dependencies.db_session),
        redis: rds.RedisClient = Depends(dependencies.redis),
    ):
        """Browse the data paths. The top level lists the data paths themselves."""
        if sort_order is None:
            sort_order = "asc" if sort_by == "name" else "desc"

        entity_id = scope.entity_id(request)
        current_path = _subpath(subpath)
        data_paths = scope.data_paths(session, entity_id)
        browser = scope.browser(entity_id, data_paths, redis)

        # a folder below the data paths that is gone, e.g. a stale search result
        missing = (
            page == 0 and bool(current_path.parts)
            and any(current_path == Path(dp.path) or current_path.is_relative_to(dp.path) for dp in data_paths)
            and not (browser.root_dir / current_path).is_dir()
        )
        if missing:
            fs_index.touch(redis, current_path)

        limit: int | None = DATA_BROWSER_PAGE_LIMIT
        if is_root_listing := not current_path.parts:
            limit = None
            paths = browser.list_roots(sort_by=sort_by, sort_order=sort_order)
        else:
            paths = browser.list_contents(
                current_path,
                limit=limit,
                offset=page * DATA_BROWSER_PAGE_LIMIT,
                sort_by=sort_by,
                sort_order=sort_order,
            )

        # mark the entries that are data paths themselves (usually the top level, but nested ones too),
        # which are highlighted and the only ones insiders can remove
        by_path = _by_path(data_paths)
        for browser_path in paths:
            browser_path.data_paths = by_path.get(browser_path.rel_path.as_posix(), [])

        return responses.htmx_response(
            template="components/file-browser/entries.html",
            paths=paths,
            current_path=current_path,
            limit=limit,
            current_page=page,
            sort_by=sort_by,
            sort_order=sort_order,
            share_token=None,
            entries_route=f"{scope.entity}_browser_entries",
            route_params={scope.id_param: entity_id},
            file_route=f"serve_{scope.entity}_file",
            servable_extensions=PROJECT_SERVABLE_EXTENSIONS,
            highlight_data_paths=True,
            remove_route=f"remove_{scope.entity}_data_path" if current_user.can_assign_data else None,
            data_owner_label=scope.label,
            is_root_listing=is_root_listing,
            location_header=located and page == 0,
            missing=missing,
        )

    @router.get(f"{id_path}/data-search", name=f"{scope.entity}_browser_search")
    def browser_search(
        request: Request,
        q: str = Query("", max_length=512),
        kind: Literal["all", "dirs", "files"] = Query("all"),
        page: int = Query(0, ge=0),
        _: C.AccessLevel = Depends(scope.permissions),
        session: SyncSession = Depends(dependencies.db_session),
        fs_index_session: SyncSession | None = Depends(dependencies.fs_index_session),
        redis: rds.RedisClient = Depends(dependencies.redis),
    ):
        """Searches the fs-index within the data paths, showing only what a share link of them would serve."""
        entity_id = scope.entity_id(request)
        data_paths = scope.data_paths(session, entity_id)
        browser = scope.browser(entity_id, data_paths, redis)
        entries, has_more, error = [], False, None
        if fs_index_session is None:
            error = "unavailable"
        else:
            try:
                entries, has_more = fs_index.search_page(
                    fs_index_session, q, page=page, kind=kind,
                    prefixes=[data_path.path for data_path in data_paths], visible_only=True,
                )
            except fs_index.QueryTooShort:
                error = "too_short"

        # the index can lag behind .ngsignore edits and symlink changes: check the (few) results live
        results = [result for result in fs_index.to_results(entries, q) if browser.is_safe(Path(result.path))]
        by_path = _by_path(data_paths)
        for result in results:
            result.data_paths = by_path.get(result.path, [])

        return responses.htmx_response(
            template="components/file-browser/search-results.html",
            results=results,
            query=q,
            kind=kind,
            root=None,
            roots=[],
            page=page,
            has_more=has_more,
            error=error,
            min_term_length=fs_index.MIN_TERM_LENGTH,
            indexed_at=fs_index.indexed_at(fs_index_session),
            search_route=f"{scope.entity}_browser_search",
            entries_route=f"{scope.entity}_browser_entries",
            route_params={scope.id_param: entity_id},
            file_route=f"serve_{scope.entity}_file",
            servable_extensions=PROJECT_SERVABLE_EXTENSIONS,
            insider_actions=False,
            data_owner_label=scope.label,
        )

    @router.get(f"{id_path}/files/{{subpath:path}}", name=f"serve_{scope.entity}_file")
    def serve_file(
        request: Request,
        subpath: str,
        _: C.AccessLevel = Depends(scope.permissions),
        session: SyncSession = Depends(dependencies.db_session),
        redis: rds.RedisClient = Depends(dependencies.redis),
    ):
        """Serve a file under the data paths. The URL mirrors the share root, so relative links in HTML reports resolve."""
        entity_id = scope.entity_id(request)
        browser = scope.browser(entity_id, scope.data_paths(session, entity_id), redis)
        if (path := browser.get_file(_subpath(subpath))) is None:
            raise exc.NotFoundException("File not found. It may have been moved or deleted recently.")
        if not is_servable(path):
            raise exc.NoPermissionsException("This file can only be downloaded through a data share link.")

        mimetype = servable_mimetype(path)
        return responses.file_response(
            path=path,
            filename=path.name,
            content_type=mimetype,
            disposition="inline" if is_browser_friendly(mimetype) else "attachment",
            require_accel=True,
        )

    return router
