import json

import inspect
import itertools
from pathlib import Path
from types import NoneType, UnionType
from typing import get_type_hints, get_origin, get_args, Any, Callable, Literal

from flask import Request

from opengsync_db import models

from .. import logger


def __generate_routes(base: str, parts: list[tuple[str, str]], defaults: dict[str, int | str | None]):
    routes = []
    param_names = list(defaults.keys())

    for r in range(len(param_names) + 1):
        for omit_keys in itertools.combinations(param_names, r):
            path_parts = [
                f"<{converter}:{name}>"
                for name, converter in parts
                if name not in omit_keys
            ]
            route_path = f"/{base}/" + "/".join(path_parts)
            route_defaults = {k: defaults[k] for k in omit_keys}
            routes.append((route_path, route_defaults))

    return routes


def infer_route(
    func: Callable,
    arg_params: list[str], form_params: list[str], json_params: list[str],
    base: str | None = None,
) -> tuple[list[tuple[str, dict[str, int | str | None]]], Literal["required", "optional", "no"], dict[str, dict[str, type]]]:
    parameters = dict(inspect.signature(func).parameters)
    hints = get_type_hints(func)
    params: dict[str, dict[str, type]] = {
        "args": {},
        "form": {},
        "json": {},
        "url": {},
    }

    base = base or func.__name__
    base = base.lstrip("/").rstrip("/")

    parts: list[tuple[str, str]] = []
    defaults: dict[str, int | str | None] = {}
    routes = []

    current_user_required = "no"
    try:
        if (param := parameters.pop("current_user")) is not None:
            if (type_hint := hints.get("current_user", None)) == models.User:
                current_user_required = "required"
            elif get_origin(type_hint) == UnionType:
                current_user_required = "optional"
    except KeyError:
        pass

    for name, param in parameters.items():
        if name in arg_params:
            params["args"][name] = hints.get(name, str)
        elif name in form_params:
            params["form"][name] = hints.get(name, str)
        elif name in json_params:
            params["json"][name] = hints.get(name, str)
        else:
            params["url"][name] = hints.get(name, str)

            type_hint = hints.get(name, str)
            origin = get_origin(type_hint)
            args = get_args(type_hint)

            if type_hint == int:
                converter = "int"
            elif type_hint == str:
                converter = "string"
            elif origin is Literal:
                if all(isinstance(a, str) for a in args):
                    converter = "string"
                elif all(isinstance(a, int) for a in args):
                    converter = "int"
                else:
                    raise ValueError(f"Unsupported Literal types: {args}")
            elif origin is UnionType:
                non_none_args = [a for a in args if a is not NoneType]
                if len(non_none_args) == 1:
                    base_type = non_none_args[0]
                    if base_type == int:
                        converter = "int"
                    elif base_type == str:
                        converter = "string"
                    else:
                        raise ValueError(f"Unsupported Optional base type: {base_type}")
                else:
                    raise ValueError(f"Unsupported Union types: {args}")
            elif type_hint == Path:
                converter = "path"
            else:
                raise ValueError(f"Unsupported type hint: {type_hint} ({name}), {origin}")

            if param.default != inspect.Parameter.empty:
                defaults[name] = param.default

            parts.append((name, converter))

    routes = []

    for route, defs in __generate_routes(base, parts, defaults):
        routes.append((route, defs))
        
    return routes, current_user_required, params


def validate_argument(value: Any, name: str, type_hint, origin, args):
    if type_hint == int:
        value = int(value)
    elif type_hint == str:
        value = str(value)
    elif origin is Literal:
        if all(isinstance(a, str) for a in args):
            value = str(value)
        elif all(isinstance(a, int) for a in args):
            value = int(value)
        else:
            raise ValueError(f"Unsupported Literal types: {args}")
    elif origin is UnionType:
        non_none_args = [a for a in args if a is not NoneType]
        if len(non_none_args) == 1:
            base_type = non_none_args[0]
            if base_type == int:
                if value is not None:
                    value = int(value)
            elif base_type == str:
                if value is not None:
                    value = str(value)
            elif base_type == dict:
                if isinstance(value, str):
                    value = json.loads(value)
                elif not isinstance(value, dict):
                    raise ValueError(f"Expected dict or JSON string for parameter: {name}")
            else:
                raise ValueError(f"Unsupported Optional base type: {base_type}")
        else:
            raise ValueError(f"Unsupported Union types: {args}")
    elif type_hint == Path:
        value = Path(value)
    else:
        raise ValueError(f"Unsupported type hint: {type_hint} ({name}), {origin}")
    
    return value
    

def validate_parameters(func: Callable, request: Request, kwargs: dict) -> tuple[dict, dict]:
    sig = inspect.signature(func)
    hints = get_type_hints(func)

    args = dict(request.args)
    form = dict(request.form | request.files)
    json_data: dict = request.get_json(silent=True) or {}

    additional_kwargs = args | form | json_data

    for name, param in sig.parameters.items():
        additional_kwargs.pop(name, None)
        if name in kwargs:
            continue
        
        if name in args:
            value = args.get(name)
        elif name in form:
            value = form.get(name)
        elif name in json_data:
            value = json_data.get(name)
        else:
            if param.default != inspect.Parameter.empty:
                kwargs[name] = param.default
                continue
            else:
                raise ValueError(f"Missing required parameter: {name}")
            
        type_hint = hints.get(name, str)

        value = validate_argument(value, name, type_hint, get_origin(type_hint), get_args(type_hint))
        kwargs[name] = value

    return kwargs, additional_kwargs
    
    