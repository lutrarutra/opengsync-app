import inspect
import json
import itertools
from pathlib import Path
from types import NoneType, UnionType
from typing import get_type_hints, get_origin, get_args, Any, Callable, Literal

from opengsync_db import models

from .. import logger

def __generate_routes(base: str, parts: list[tuple[str, str]], defaults: dict[str, int | str | None]):
    routes = []

    param_names = list(defaults.keys())

    # Generate all subsets of defaulted parameters to be omitted
    for r in range(len(param_names) + 1):
        for omit_keys in itertools.combinations(param_names, r):
            # Build path excluding omitted parameters
            path_parts = [
                f"<{converter}:{name}>"
                for name, converter in parts
                if name not in omit_keys
            ]
            route_path = f"/{base}/" + "/".join(path_parts)
            route_defaults = {k: defaults[k] for k in omit_keys}
            routes.append((route_path, route_defaults))

    return routes


def infer_route(func: Callable, base: str | None = None) -> tuple[list[tuple[str, dict[str, int | str | None]]], Literal["required", "optional", "no"]]:
    parameters = dict(inspect.signature(func).parameters)
    hints = get_type_hints(func)
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
        if name.startswith("_"):
            continue
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
                # It's Optional[<type>]
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
        
    return routes, current_user_required


def validate_arguments(fnc: Callable[..., Any], arguments: dict) -> dict:
    sig = inspect.signature(fnc)
    hints = get_type_hints(fnc)
    validated_args = {}

    for name, param in sig.parameters.items():
        if not name.startswith("_"):
            continue

        if name not in arguments:
            if param.default != inspect.Parameter.empty:
                validated_args[name] = param.default
            else:
                raise ValueError(f"Missing required argument: {name}")
            continue
        
        type_hint = hints.get(name, str)
        origin = get_origin(type_hint)
        args = get_args(type_hint)

        value = arguments[name]
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
                    value = int(value)
                elif base_type == str:
                    value = str(value)
                else:
                    raise ValueError(f"Unsupported Optional base type: {base_type}")
            else:
                raise ValueError(f"Unsupported Union types: {args}")
        elif type_hint == Path:
            value = Path(value)
        else:
            raise ValueError(f"Unsupported type hint: {type_hint} ({name}), {origin}")
        
        validated_args[name] = value
            
    return validated_args
    
    
