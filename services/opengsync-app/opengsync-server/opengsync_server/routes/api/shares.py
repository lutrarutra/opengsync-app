from pathlib import Path

from flask import Blueprint, jsonify

from opengsync_db.categories import DataPathType


from ...core import wrappers, exceptions, runtime
from ... import db, logger


shares_api_bp = Blueprint("shares_api", __name__, url_prefix="/api/shares/")

def get_share_path(real_path: str) -> Path | None:
    for key, prefix in runtime.app.share_path_mapping.items():
        if real_path.startswith(prefix):
            if not real_path.replace(prefix, "", 1):
                raise exceptions.BadRequestException(f"Path '{real_path}' is the root of share path mapping '{key}' and is not allowed.")
            return Path(key) / real_path.replace(prefix, "", 1)
    return None

def get_real_path(share_path: str) -> str | None:
    for key, prefix in runtime.app.share_path_mapping.items():
        if share_path.startswith(key):
            return share_path.replace(key, prefix, 1)
    return None
    

@wrappers.api_route(shares_api_bp, db=db, methods=["POST"], json_params=["project_id", "path", "path_type_id"])
def add_data_path_to_project(project_id: int, path: str, path_type_id: int = 0):
    path = Path(path).resolve().as_posix()

    try:
        path_type = DataPathType.get(path_type_id)
    except ValueError:
        raise exceptions.BadRequestException(f"Invalid path type ID '{path_type_id}'.")
    
    if not Path(path).is_absolute():
        raise exceptions.BadRequestException(f"Path '{path}' is not an absolute path.")
    
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException(f"Project with ID '{project_id}' not found.")
    
    if (share_path := get_share_path(path)) is None:
        raise exceptions.BadRequestException(f"Invalid share path '{path}'. Path must start with one of: {', '.join(runtime.app.share_path_mapping.values())}")
    
    if not (p := runtime.app.share_root / share_path).exists():
        raise exceptions.NotFoundException(f"Share path '{path}' does not exist on server.")
    
    # make sure path does not .. out of share root
    try:
        p.resolve().relative_to(runtime.app.share_root.resolve())
    except ValueError:
        raise exceptions.BadRequestException(f"Path '{path}' is outside of share root.")
    
    share_path = p.relative_to(runtime.app.share_root).as_posix()

    logger.debug(share_path)

    if p.is_dir() and path_type != DataPathType.DIRECTORY:
        raise exceptions.BadRequestException(f"Path '{path}' is a directory, but path type is not DIRECTORY.")
    
    if not p.is_dir() and path_type == DataPathType.DIRECTORY:
        raise exceptions.BadRequestException(f"Path '{path}' is not a directory, but path type is DIRECTORY.")
    
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

    return jsonify({"result": "success", "share_path": share_path, "path": path, "type": path_type.name}), 200

@wrappers.api_route(shares_api_bp, db=db, methods=["DELETE"], json_params=["project_id"])
def remove_data_paths_from_project(project_id: int):    
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException(f"Project with ID '{project_id}' not found.")
    
    data_paths, _ = db.data_paths.find(project_id=project.id)
    paths = []
    for data_path in data_paths:
        db.data_paths.delete(data_path)
        exists = (runtime.app.share_root / data_path.path).exists()
        paths.append((data_path.path, get_real_path(data_path.path), exists))
    
    return jsonify({"result": "success", "paths": paths}), 200
