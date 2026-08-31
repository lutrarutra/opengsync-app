from pathlib import Path
from typing import Any, Literal

import mimetypes
import smtplib
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import orm

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import dependencies, exceptions as exc, config, responses, templates
from ...core.mailer import Mailer
from ...utils import parsing
from ...utils.io import is_browser_friendly
from ...utils.shared_file_browser import SharedFileBrowser

router = APIRouter(prefix="/shares", tags=["api", "shares"])


def _share_path_mapping() -> dict[str, str]:
    mapping = config.settings.app_config.share_path_mapping
    if mapping is None:
        raise exc.BadRequestException("Share path mapping is not configured.")
    return mapping.model_dump()


def get_share_path(real_path: str) -> Path | None:
    key_value = list(_share_path_mapping().items())
    key_value.sort(key=lambda x: len(x[1]), reverse=True)

    rp = Path(real_path).resolve()

    for key, prefix in key_value:
        if rp.is_relative_to(prefix):
            if not real_path.replace(prefix, "", 1):
                raise exc.BadRequestException(
                    f"Path '{real_path}' is the root of share path mapping '{key}' and is not allowed."
                )
            return Path(key) / real_path.replace(prefix, "", 1).lstrip("/")
    return None


def get_real_path(share_path: str) -> str | None:
    mapping = config.settings.app_config.share_path_mapping
    if mapping is None:
        return None
    key_value = list(mapping.model_dump().items())
    key_value.sort(key=lambda x: len(x[1]), reverse=True)
    sp = Path(share_path).resolve()

    for key, prefix in key_value:
        if sp.is_relative_to(key):
            return share_path.replace(key, prefix, 1)
    return None


def resolve_share_path(path: str, path_type: C.DataPathType) -> tuple[str, C.DataPathType]:
    path = Path(path).resolve().as_posix()

    if not Path(path).is_absolute():
        raise exc.BadRequestException(f"Path '{path}' is not an absolute path.")

    if (share_path := get_share_path(path)) is None:
        prefixes = ", ".join(_share_path_mapping().values())
        raise exc.BadRequestException(f"Invalid share path '{path}'. Path must start with one of: {prefixes}")

    share_root = Path(config.settings.app_config.share_root)
    if not (p := share_root / share_path).exists():
        raise exc.NotFoundException(
            f"Share path '{share_path}' ({path} -> {p.as_posix()}) does not exist on server."
        )

    try:
        p.resolve().relative_to(share_root.resolve())
    except ValueError:
        raise exc.BadRequestException(f"Path '{path}' is outside of share root.")

    if p.is_dir() and path_type != C.DataPathType.DIRECTORY:
        raise exc.BadRequestException(f"Path '{path}' is a directory, but path type is not DIRECTORY.")

    if not p.is_dir() and path_type == C.DataPathType.DIRECTORY:
        raise exc.BadRequestException(f"Path '{path}' is not a directory, but path type is DIRECTORY.")

    return p.relative_to(share_root).as_posix(), path_type


def _infer_path_type(path: str) -> C.DataPathType:
    p = Path(path)
    if p.is_dir():
        return C.DataPathType.DIRECTORY
    match p.suffix.lower().lstrip("."):
        case "pdf":
            return C.DataPathType.PDF
        case "tsv" | "csv":
            return C.DataPathType.TABLE
        case "xlsx" | "xls":
            return C.DataPathType.EXCEL
        case "png" | "jpg" | "jpeg":
            return C.DataPathType.IMAGE
        case "html":
            return C.DataPathType.HTML
        case _:
            return C.DataPathType.CUSTOM


def _attach_data_path(
    session: SyncSession,
    share_path: str,
    path_type: C.DataPathType,
    *,
    project: models.Project | None = None,
    seq_request: models.SeqRequest | None = None,
    experiment: models.Experiment | None = None,
    library: models.Library | None = None,
) -> None:
    create_kwargs: dict[str, Any] = {"path": share_path, "type": path_type}
    stmt = Q.data_path.select(path=share_path)

    if project is not None:
        stmt = Q.data_path.select(project_id=project.id, statement=stmt)
        create_kwargs["project"] = project
    if seq_request is not None:
        stmt = Q.data_path.select(seq_request_id=seq_request.id, statement=stmt)
        create_kwargs["seq_request"] = seq_request
    if experiment is not None:
        stmt = Q.data_path.select(experiment_id=experiment.id, statement=stmt)
        create_kwargs["experiment"] = experiment
    if library is not None:
        stmt = Q.data_path.select(library_id=library.id, statement=stmt)
        create_kwargs["library"] = library

    if (data_path := session.first(stmt)) is not None:
        data_path.type = path_type
        session.save(data_path)
    else:
        session.save(Q.data_path.create(**create_kwargs))


def _collect_deleted_paths(session: SyncSession, data_paths: list[models.DataPath]) -> list[tuple[str, str | None, bool]]:
    share_root = Path(config.settings.app_config.share_root)
    paths: list[tuple[str, str | None, bool]] = []
    for data_path in data_paths:
        session.delete(data_path)
        exists = (share_root / data_path.path).exists()
        paths.append((data_path.path, get_real_path(data_path.path), exists))
    return paths


class AddDataPathRequest(BaseModel):
    path: str
    seq_request_id: int | None = None
    project_id: int | None = None
    experiment_id: int | None = None
    library_id: int | None = None
    path_type_id: int | None = None


class RemoveDataPathsRequest(BaseModel):
    project_id: int | None = None
    seq_request_id: int | None = None
    experiment_id: int | None = None
    library_id: int | None = None


class ReleaseProjectDataRequest(BaseModel):
    project_id: int
    internal_access: bool
    time_valid_min: int
    anonymous_send: bool = False
    recipients: list[str] | None = None
    mark_project_delivered: bool | None = None
    comment: str | None = None


@router.post("/add-data_path", dependencies=[Depends(dependencies.require_insider)])
def add_data_path(
    body: AddDataPathRequest,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict[str, Any]:
    if body.path_type_id is not None:
        try:
            path_type = C.DataPathType.get(body.path_type_id)
        except ValueError:
            raise exc.BadRequestException(f"Invalid path type ID '{body.path_type_id}'.")
    else:
        path_type = _infer_path_type(body.path)

    share_path, path_type = resolve_share_path(body.path, path_type)

    if body.project_id is not None:
        if (project := session.first(Q.project.select(id=body.project_id))) is None:
            raise exc.NotFoundException(f"Project with ID '{body.project_id}' not found.")
        _attach_data_path(session, share_path, path_type, project=project)

    if body.seq_request_id is not None:
        if (seq_request := session.first(Q.seq_request.select(id=body.seq_request_id))) is None:
            raise exc.NotFoundException(f"Seq Request with ID '{body.seq_request_id}' not found.")
        _attach_data_path(session, share_path, path_type, seq_request=seq_request)

    if body.experiment_id is not None:
        if (experiment := session.first(Q.experiment.select(id=body.experiment_id))) is None:
            raise exc.NotFoundException(f"Experiment with ID '{body.experiment_id}' not found.")
        _attach_data_path(session, share_path, path_type, experiment=experiment)

    if body.library_id is not None:
        if (library := session.first(Q.library.select(id=body.library_id))) is None:
            raise exc.NotFoundException(f"Library with ID '{body.library_id}' not found.")
        _attach_data_path(session, share_path, path_type, library=library)

    return {"result": "success", "share_path": share_path, "path": body.path, "type": path_type.name}


@router.delete("/remove-data_paths", dependencies=[Depends(dependencies.require_insider)])
def remove_data_paths(
    body: RemoveDataPathsRequest,
    session: SyncSession = Depends(dependencies.db_session),
) -> dict[str, Any]:
    paths: list[tuple[str, str | None, bool]] = []
    if body.project_id is not None:
        if (project := session.first(
            Q.project.select(id=body.project_id),
            options=[orm.selectinload(models.Project.data_paths)],
        )) is None:
            raise exc.NotFoundException(f"Project with ID '{body.project_id}' not found.")
        paths.extend(_collect_deleted_paths(session, project.data_paths))

    if body.seq_request_id is not None:
        if (seq_request := session.first(
            Q.seq_request.select(id=body.seq_request_id),
            options=[orm.selectinload(models.SeqRequest.data_paths)],
        )) is None:
            raise exc.NotFoundException(f"Seq Request with ID '{body.seq_request_id}' not found.")
        paths.extend(_collect_deleted_paths(session, seq_request.data_paths))

    if body.experiment_id is not None:
        if (experiment := session.first(
            Q.experiment.select(id=body.experiment_id),
            options=[orm.selectinload(models.Experiment.data_paths)],
        )) is None:
            raise exc.NotFoundException(f"Experiment with ID '{body.experiment_id}' not found.")
        paths.extend(_collect_deleted_paths(session, experiment.data_paths))

    if body.library_id is not None:
        if (library := session.first(
            Q.library.select(id=body.library_id),
            options=[orm.selectinload(models.Library.data_paths)],
        )) is None:
            raise exc.NotFoundException(f"Library with ID '{body.library_id}' not found.")
        paths.extend(_collect_deleted_paths(session, library.data_paths))

    return {"result": "success", "paths": paths}


@router.post("/release-project_data")
def release_project_data(
    body: ReleaseProjectDataRequest,
    session: SyncSession = Depends(dependencies.db_session),
    mailer: Mailer = Depends(dependencies.mail_client),
    current_user: models.User = Depends(dependencies.require_insider),
) -> dict[str, Any]:

    project = session.first(
        Q.project.select(id=body.project_id),
        options=[
            orm.selectinload(models.Project.data_paths),
            orm.selectinload(models.Project.share_token),
            orm.selectinload(models.Project.libraries),
        ],
    )
    if project is None:
        raise exc.NotFoundException(f"Project with ID '{body.project_id}' not found.")

    if project.identifier is None:
        raise exc.BadRequestException("Project must have an identifier to release data.")

    paths = parsing.filter_subpaths([data_path.path for data_path in project.data_paths])
    if len(paths) == 0:
        raise exc.BadRequestException("No data paths associated with project to share.")

    if (share_token := project.share_token) is not None and not share_token._expired:
        share_token._expired = True
        session.save(share_token)

    share_token = session.save(Q.share_token.create(
        owner=current_user,
        time_valid_min=body.time_valid_min,
        paths=paths,
    ), flush=True)

    recipients = body.recipients
    if recipients is None:
        recipients = session.pd.get_project_latest_request_share_emails(project.id)["email"].unique().tolist()

    recipients = list(set(recipients))
    if len(recipients) == 0:
        raise exc.BadRequestException(
            "No recipients specified and no emails found in latest sequencing request share-tab."
        )

    project.share_token = share_token
    session.save(project)

    if config.settings.ENVIRONMENT == "prod":
        try:
            mailer.send_share_project_data(
                recipients=recipients,
                share_token=share_token,
                current_user=current_user,
                project=project,
                internal_share=body.internal_access,
                anonymous=body.anonymous_send,
                comment=body.comment,
            )
        except smtplib.SMTPException as e:
            logger.error(f"Failed to send email to {recipients}: {e}")
            raise
    else:
        logger.info(f"Email would be sent to: {recipients}")

    seq_requests = session.get_all(
        Q.seq_request.select(project_id=project.id),
        options=[
            orm.selectinload(models.SeqRequest.delivery_email_links),
            orm.selectinload(models.SeqRequest.libraries),
        ],
        limit=None,
    )

    if body.mark_project_delivered is None:
        all_libraries_delivered = True
        for seq_request in seq_requests:
            for library in seq_request.libraries:
                if library.status < C.LibraryStatus.SEQUENCED:
                    all_libraries_delivered = False
                    break
            if not all_libraries_delivered:
                break
        if all_libraries_delivered and project.status < C.ProjectStatus.DELIVERED:
            project.status = C.ProjectStatus.DELIVERED
            session.save(project)
    elif body.mark_project_delivered and project.status < C.ProjectStatus.DELIVERED:
        project.status = C.ProjectStatus.DELIVERED
        session.save(project)

    for seq_request in seq_requests:
        for link in seq_request.delivery_email_links:
            if link.email in recipients:
                link.status = C.DeliveryStatus.DISPATCHED
        session.save(seq_request)

    for library in project.libraries:
        if library.status == C.LibraryStatus.SEQUENCED:
            library.status = C.LibraryStatus.SHARED
            session.save(library)

    return {"result": "success", "recipients": recipients}


def _subpath(subpath: str) -> Path:
    if not subpath or subpath in (".", "/"):
        return Path()
    return Path(subpath)


def _load_share_token(session: SyncSession, token: str) -> models.ShareToken:
    if (share_token := session.first(Q.share_token.select(uuid=token).options(orm.selectinload(models.ShareToken.paths)))) is None:
        raise exc.NotFoundException("Token Not Found")
    if share_token.is_expired:
        raise exc.NoPermissionsException("Token expired")
    return share_token


@router.get("/validate/{token}", name="file_share.validate")
def validate(token: str, session: SyncSession = Depends(dependencies.db_session)):
    _load_share_token(session, token)
    return PlainTextResponse("OK")


@router.get("/rclone/{token}", name="file_share.rclone", operation_id="file_share_rclone")
@router.get("/rclone/{token}/{subpath:path}", name="file_share.rclone", operation_id="file_share_rclone_path")
def rclone(
    token: str,
    subpath: str = "",
    session: SyncSession = Depends(dependencies.db_session),
):
    current_path = _subpath(subpath)
    share_token = _load_share_token(session, token)
    SHARE_ROOT = Path(config.settings.app_config.share_root)
    browser = SharedFileBrowser(root_dir=SHARE_ROOT, share_token=share_token)

    if len(paths := browser.list_contents(current_path)) == 0 and (file := browser.get_file(current_path)) is not None:
        mimetype = mimetypes.guess_type(file)[0] or "application/octet-stream"
        return responses.file_response(
            file,
            filename=file.name,
            content_type=mimetype,
            disposition="attachment" if config.settings.ENVIRONMENT != "prod" else None,
        )

    return responses.html_response(
        "share/rclone.html",
        current_path=current_path,
        parent_dir=current_path.parent if current_path != Path() else None,
        paths=paths,
        token=token,
    )


@router.get("/browse/{token}", name="file_share.browse", operation_id="file_share_browse")
@router.get("/browse/{token}/{subpath:path}", name="file_share.browse", operation_id="file_share_browse_path")
def browse(
    token: str,
    subpath: str = "",
    session: SyncSession = Depends(dependencies.db_session),
):
    current_path = _subpath(subpath)
    share_token = _load_share_token(session, token)
    SHARE_ROOT = Path(config.settings.app_config.share_root)
    browser = SharedFileBrowser(root_dir=SHARE_ROOT, share_token=share_token)

    if len(paths := browser.list_contents(current_path)) == 0 and (file := browser.get_file(current_path)) is not None:
        mimetype = mimetypes.guess_type(file)[0] or "application/octet-stream"
        return responses.file_response(
            file,
            filename=file.name,
            content_type=mimetype,
            disposition="inline" if is_browser_friendly(mimetype) else "attachment",
        )

    paths = sorted(paths, key=lambda p: p.name.lower())

    return responses.html_response(
        "share/browse.html",
        current_path=current_path,
        parent_dir=current_path.parent if current_path != Path() else None,
        paths=paths,
        token=token,
    )


@router.get("/rclone_script/{token}", name="file_share.rclone_script")
def rclone_script(token: str, session: SyncSession = Depends(dependencies.db_session)):
    share_token = _load_share_token(session, token)
    sync_command = templates.render_template("snippets/rclone-sync.sh.j2", token=share_token.uuid, outdir="BSF_DATA")
    return Response(content=sync_command, media_type="text/plain")


@router.get("/curl_script/{token}/{platform}", name="file_share.curl_script")
def curl_script(
    token: str,
    platform: Literal["windows", "unix"],
    session: SyncSession = Depends(dependencies.db_session),
):
    if platform == "unix":
        template = "snippets/curl-download.sh.j2"
    elif platform == "windows":
        template = "snippets/curl-download.ps1.j2"
    else:
        raise exc.BadRequestException("Invalid platform")

    share_token = _load_share_token(session, token)
    SHARE_ROOT = Path(config.settings.app_config.share_root)
    browser = SharedFileBrowser(root_dir=SHARE_ROOT, share_token=share_token)
    current_path = Path()
    items = []
    for rel_path, is_dir in browser.walk_contents(current_path):
        try:
            display_path = rel_path.relative_to(current_path) if current_path != Path() else rel_path
        except ValueError:
            display_path = rel_path

        url = str(responses.url_for("file_share.rclone", token=token, subpath=rel_path.as_posix()))

        items.append({
            "rel_path": display_path.as_posix(),
            "is_dir": is_dir,
            "url": url,
        })

    rendered_script = templates.render_template(
        template, base_folder=current_path.name if current_path.name else "download", items=items
    )

    return Response(
        rendered_script,
        media_type="text/x-shellscript",
        headers={"Content-Disposition": f"attachment; filename=sync_{current_path.name or 'all'}.sh"},
    )

