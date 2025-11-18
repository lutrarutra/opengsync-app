from pathlib import Path

from flask import Blueprint, jsonify

from opengsync_db.categories import DataPathType, DataPathTypeEnum


from ...core import wrappers, exceptions, runtime
from ... import db, logger


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


def resolve_share_path(path: str, path_type_id: int) -> tuple[str, DataPathTypeEnum]:
    path = Path(path).resolve().as_posix()
    try:
        path_type = DataPathType.get(path_type_id)
    except ValueError:
        raise exceptions.BadRequestException(f"Invalid path type ID '{path_type_id}'.")
    
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
    

@wrappers.api_route(shares_api_bp, db=db, methods=["POST"], json_params=["project_id", "seq_request_id", "experiment_id", "library_id", "path", "path_type_id"])
def add_data_path(
    path: str, path_type_id: int,
    seq_request_id: int | None = None,
    project_id: int | None = None,
    experiment_id: int | None = None,
    library_id: int | None = None,
):
    share_path, path_type = resolve_share_path(path, path_type_id)
    
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
