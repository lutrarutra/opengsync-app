import os
from pathlib import Path
import smtplib

from flask import Blueprint, jsonify, render_template

from opengsync_db.categories import DataPathType, DataPathTypeEnum, LibraryType, ProjectStatus, DeliveryStatus
from opengsync_db import models

from ...tools import utils
from ...core import wrappers, exceptions, runtime
from ... import db, logger, mail_handler


shares_api_bp = Blueprint("shares_api", __name__, url_prefix="/api/shares/")

def get_share_path(real_path: str) -> Path | None:
    # sort by length of prefix descending to match longest prefix first
    key_value = list(runtime.app.share_path_mapping.items())
    key_value.sort(key=lambda x: len(x[1]), reverse=True)

    rp = Path(real_path).resolve()

    for key, prefix in key_value:
        if rp.is_relative_to(prefix):
            if not real_path.replace(prefix, "", 1):
                raise exceptions.BadRequestException(f"Path '{real_path}' is the root of share path mapping '{key}' and is not allowed.")
            share_path = Path(key) / real_path.replace(prefix, "", 1).lstrip("/")
            return share_path
    return None

def get_real_path(share_path: str) -> str | None:
    # sort by length of prefix descending to match longest prefix first
    key_value = list(runtime.app.share_path_mapping.items())
    key_value.sort(key=lambda x: len(x[1]), reverse=True)
    sp = Path(share_path).resolve()

    for key, prefix in key_value:
        if sp.is_relative_to(key):
            return share_path.replace(key, prefix, 1)
    return None


def resolve_share_path(path: str, path_type: DataPathTypeEnum) -> tuple[str, DataPathTypeEnum]:
    path = Path(path).resolve().as_posix()
    
    if not Path(path).is_absolute():
        raise exceptions.BadRequestException(f"Path '{path}' is not an absolute path.")
    
    if (share_path := get_share_path(path)) is None:
        raise exceptions.BadRequestException(f"Invalid share path '{path}'. Path must start with one of: {', '.join(runtime.app.share_path_mapping.values())}")
    
    if not (p := runtime.app.share_root / share_path).exists():
        raise exceptions.NotFoundException(f"Share path '{share_path}' ({path} -> {p.as_posix()}) does not exist on server.")
    
    # make sure path does not .. out of share root
    try:
        p.resolve().relative_to(runtime.app.share_root.resolve())
    except ValueError:
        raise exceptions.BadRequestException(f"Path '{path}' is outside of share root.")
    
    if p.is_dir() and path_type != DataPathType.DIRECTORY:
        raise exceptions.BadRequestException(f"Path '{path}' is a directory, but path type is not DIRECTORY.")

    if not p.is_dir() and path_type == DataPathType.DIRECTORY:
        raise exceptions.BadRequestException(f"Path '{path}' is not a directory, but path type is DIRECTORY.")
    
    return p.relative_to(runtime.app.share_root).as_posix(), path_type


@wrappers.api_route(shares_api_bp, db=db, methods=["POST"], json_params=["project_id", "seq_request_id", "experiment_id", "library_id", "path", "path_type_id"], limit="3/second", limit_override=True)
def add_data_path(
    path: str,
    seq_request_id: int | None = None,
    project_id: int | None = None,
    experiment_id: int | None = None,
    library_id: int | None = None,
    path_type_id: int | None = None
):
    if path_type_id is not None:
        try:
            path_type = DataPathType.get(path_type_id)
        except ValueError:
            raise exceptions.BadRequestException(f"Invalid path type ID '{path_type_id}'.")
    else:
        if (p := Path(path)).is_dir():
            path_type = DataPathType.DIRECTORY
        else:
            match p.suffix.lower().lstrip("."):
                case "pdf":
                    path_type = DataPathType.PDF
                case "tsv" | "csv":
                    path_type = DataPathType.TABLE
                case "xlsx" | "xls":
                    path_type = DataPathType.EXCEL
                case "png" | "jpg" | "jpeg":
                    path_type = DataPathType.IMAGE
                case "html":
                    path_type = DataPathType.HTML
                case _:
                    path_type = DataPathType.CUSTOM 

    share_path, path_type = resolve_share_path(path, path_type)
    
    if project_id is not None:
        if (project := db.projects.get(project_id)) is None:
            raise exceptions.NotFoundException(f"Project with ID '{project_id}' not found.")
        if len(project_data_paths := db.data_paths.find(path=share_path, project_id=project.id)[0]) > 0:
            data_path = project_data_paths[0]
            data_path.type = path_type
            db.data_paths.update(data_path)
        else:
            data_path = db.data_paths.create(
                path=share_path,
                type=path_type,
                project=project,
            )
        
    if seq_request_id is not None:
        if (seq_request := db.seq_requests.get(seq_request_id)) is None:
            raise exceptions.NotFoundException(f"Seq Request with ID '{seq_request_id}' not found.")
        
        if len(seq_request_data_paths := db.data_paths.find(path=share_path, seq_request_id=seq_request.id)[0]) > 0:
            data_path = seq_request_data_paths[0]
            data_path.type = path_type
            db.data_paths.update(data_path)
        else:
            data_path = db.data_paths.create(
                path=share_path,
                type=path_type,
                seq_request=seq_request,
            )

    if experiment_id is not None:
        if (experiment := db.experiments.get(experiment_id)) is None:
            raise exceptions.NotFoundException(f"Experiment with ID '{experiment_id}' not found.")
        
        if len(experiment_data_paths := db.data_paths.find(path=share_path, experiment_id=experiment.id)[0]) > 0:
            data_path = experiment_data_paths[0]
            data_path.type = path_type
            db.data_paths.update(data_path)
        else:
            data_path = db.data_paths.create(
                path=share_path,
                type=path_type,
                experiment=experiment,
            )

    if library_id is not None:
        if (library := db.libraries.get(library_id)) is None:
            raise exceptions.NotFoundException(f"Library with ID '{library_id}' not found.")  
        if len(library_data_paths := db.data_paths.find(path=share_path, library_id=library.id)[0]) > 0:
            data_path = library_data_paths[0]
            data_path.type = path_type
            db.data_paths.update(data_path)
        else:
            data_path = db.data_paths.create(
                path=share_path,
                type=path_type,
                library=library,
            )

    return jsonify({"result": "success", "share_path": share_path, "path": path, "type": path_type.name}), 200

@wrappers.api_route(shares_api_bp, db=db, methods=["DELETE"], json_params=["project_id"])
def remove_data_paths(
    seq_request_id: int | None = None,
    project_id: int | None = None,
    experiment_id: int | None = None,
    library_id: int | None = None
):    
    paths = []
    if project_id is not None:
        if (project := db.projects.get(project_id)) is None:
            raise exceptions.NotFoundException(f"Project with ID '{project_id}' not found.")
        
        data_paths, _ = db.data_paths.find(project_id=project.id)
        for data_path in data_paths:
            db.data_paths.delete(data_path)
            exists = (runtime.app.share_root / data_path.path).exists()
            paths.append((data_path.path, get_real_path(data_path.path), exists))

    if seq_request_id is not None:
        if (seq_request := db.seq_requests.get(seq_request_id)) is None:
            raise exceptions.NotFoundException(f"Seq Request with ID '{seq_request_id}' not found.")
        
        data_paths, _ = db.data_paths.find(seq_request_id=seq_request.id)
        for data_path in data_paths:
            db.data_paths.delete(data_path)
            exists = (runtime.app.share_root / data_path.path).exists()
            paths.append((data_path.path, get_real_path(data_path.path), exists))

    if experiment_id is not None:
        if (experiment := db.experiments.get(experiment_id)) is None:
            raise exceptions.NotFoundException(f"Experiment with ID '{experiment_id}' not found.")
        
        data_paths, _ = db.data_paths.find(experiment_id=experiment.id)
        for data_path in data_paths:
            db.data_paths.delete(data_path)
            exists = (runtime.app.share_root / data_path.path).exists()
            paths.append((data_path.path, get_real_path(data_path.path), exists))

    if library_id is not None:
        if (library := db.libraries.get(library_id)) is None:
            raise exceptions.NotFoundException(f"Library with ID '{library_id}' not found.")  
        
        data_paths, _ = db.data_paths.find(library_id=library.id)
        for data_path in data_paths:
            db.data_paths.delete(data_path)
            exists = (runtime.app.share_root / data_path.path).exists()
            paths.append((data_path.path, get_real_path(data_path.path), exists))
    
    return jsonify({"result": "success", "paths": paths}), 200

@wrappers.api_route(shares_api_bp, db=db, methods=["POST"], json_params=["project_id", "internal_access", "time_valid_min", "anonymous_send", "recipients", "mark_project_delivered"], limit="1/second", limit_override=True)
def release_project_data(current_user: models.User, recipients: list[str] | None, project_id: int, internal_access: bool, time_valid_min: int, anonymous_send: bool = False, mark_project_delivered: bool = True):
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException(f"Project with ID '{project_id}' not found.")
    
    if project.identifier is None:
        raise exceptions.BadRequestException("Project must have an identifier to release data.")
    
    paths = utils.filter_subpaths([data_path.path for data_path in project.data_paths])

    if len(paths) == 0:
        raise exceptions.BadRequestException("No data paths associated with project to share.")

    if (share_token := project.share_token) is not None:
        if not share_token._expired:
            share_token._expired = True
            db.shares.update(share_token)
    
    share_token = db.shares.create(
        owner=current_user,
        time_valid_min=time_valid_min,
        paths=paths,
    )

    if recipients is None:
        _recipients: list[str] = db.pd.get_project_latest_request_share_emails(project.id)["email"].unique().tolist()
        recipients = _recipients

    recipients = list(set(recipients))

    if len(recipients) == 0:  # type: ignore
        raise exceptions.BadRequestException("No recipients specified and no emails found in latest sequencing request share-tab.")

    project.share_token = share_token
    db.projects.update(project)

    outdir = project.identifier

    http_command = render_template("snippets/rclone-http.sh.j2", token=share_token.uuid, outdir=outdir)
    sync_command = render_template("snippets/rclone-sync.sh.j2", token=share_token.uuid, outdir=outdir)
    wget_command = render_template("snippets/wget.sh.j2", token=share_token.uuid, outdir=outdir)
    style = open(os.path.join(runtime.app.static_folder, "style/compiled/email.css")).read()

    browse_link = runtime.url_for("file_share.browse", token=share_token.uuid, _external=True)

    library_types = {library.type for library in project.libraries}
    tenx_contents = any(set(LibraryType.get_tenx_library_types()).intersection(library_types))

    seq_requests = db.seq_requests.find(project_id=project.id, limit=None, sort_by="id")[0]
    experiments = db.experiments.find(project_id=project.id, limit=None, sort_by="id")[0]

    internal_share_content = ""
    if (template := runtime.app.personalization.get("internal_share_template")):
        if os.path.exists(os.path.join(runtime.app.template_folder, template)):
            internal_paths = project.data_paths
            internal_paths = utils.filter_subpaths([data_path.path for data_path in internal_paths])
            internal_paths = [utils.replace_substrings(path, runtime.app.share_path_mapping) for path in internal_paths]
            internal_share_content = render_template(template, paths=internal_paths, project=project)
        else:
            logger.info(f"Internal share template '{template}' not found.")

    content = render_template(
        "email/share-data.html", style=style, browse_link=browse_link,
        project=project, tenx_contents=tenx_contents, library_types=library_types,
        author=None if anonymous_send else current_user if current_user.is_insider() else None,
        seq_requests=seq_requests, experiments=experiments, share_token=share_token,
        internal_access_share=internal_access,
        internal_share_content=internal_share_content,
        sync_command=sync_command,
        http_command=http_command,
        wget_command=wget_command,
        outdir=outdir
    )
    try:
        mail_handler.send_email(
            recipients=recipients,
            subject=f"[{project.identifier or f'P{project.id}'}]: {runtime.app.personalization['organization']} Shared Project Data",
            body=content, mime_type="html",
        )
    except smtplib.SMTPException as e:
        logger.error(f"Failed to send email to {recipients}: {e}")
        raise e
    
    if mark_project_delivered:
        if mark_project_delivered:
            if project.status < ProjectStatus.DELIVERED:
                project.status = ProjectStatus.DELIVERED
                db.projects.update(project)

        for seq_request in project.seq_requests:
            for link in seq_request.delivery_email_links:
                if link.email in recipients:
                    link.status = DeliveryStatus.DISPATCHED
            db.seq_requests.update(seq_request)
        
    return jsonify({"result": "success", "recipients": recipients}), 200

