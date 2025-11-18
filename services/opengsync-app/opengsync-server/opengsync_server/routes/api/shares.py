from pathlib import Path

from flask import Blueprint, Response, jsonify

from opengsync_db import models, exceptions as dbexc
from opengsync_db.categories import DataPathType


from ...core import wrappers, exceptions, runtime
from ... import db


shares_api_bp = Blueprint("shares_api", __name__, url_prefix="/api/shares/")

def get_share_path(real_path: str) -> str | None:
    for key, prefix in runtime.app.share_path_mapping.items():
        if real_path.startswith(prefix):
            return key
    return None

def get_real_path(share_path: str) -> str | None:
    for key, prefix in runtime.app.share_path_mapping.items():
        if share_path.startswith(key):
            return share_path.replace(key, prefix, 1)
    return None
    

@wrappers.api_route(shares_api_bp, db=db, methods=["POST"], json_params=["api_token", "project_id", "path"])
def add_data_path_to_project(api_token: str, project_id: int, path: str, path_type_id: int = 0):
    if (token := db.api_tokens.get(api_token)) is None:
        raise exceptions.NotFoundException(f"Invalid API token '{api_token}'.")
    
    try:
        path_type = DataPathType.get(path_type_id)
    except ValueError:
        raise exceptions.BadRequestException(f"Invalid path type ID '{path_type_id}'.")
    
    if not Path(path).is_absolute():
        raise exceptions.BadRequestException(f"Path '{path}' is not an absolute path.")
        
    if token.is_expired:
        raise exceptions.NoPermissionsException("API token is expired.")
    
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException(f"Project with ID '{project_id}' not found.")
    
    if (share_path := get_share_path(path)) is None:
        raise exceptions.BadRequestException(f"Invalid share path '{path}'. Path must start with one of: {', '.join(runtime.app.share_path_mapping.values())}")
    
    if not (p := runtime.app.share_root / share_path).exists():
        raise exceptions.NotFoundException(f"Share path '{path}' does not exist on server.")
    
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

@wrappers.api_route(shares_api_bp, db=db, methods=["DELETE"], json_params=["api_token", "project_id"])
def remove_data_paths_from_project(api_token: str, project_id: int):
    if (token := db.api_tokens.get(api_token)) is None:
        raise exceptions.NotFoundException(f"Invalid API token '{api_token}'.")
    
    if token.is_expired:
        raise exceptions.NoPermissionsException("API token is expired.")
    
    if (project := db.projects.get(project_id)) is None:
        raise exceptions.NotFoundException(f"Project with ID '{project_id}' not found.")
    
    data_paths, _ = db.data_paths.find(project_id=project.id)
    paths = []
    for data_path in data_paths:
        db.data_paths.delete(data_path)
        exists = (runtime.app.share_root / data_path.path).exists()
        paths.append((data_path.path, get_real_path(data_path.path), exists))
    
    return jsonify({"result": "success", "paths": paths}), 200
