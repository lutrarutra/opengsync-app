import string
import re
import json
import unicodedata
import difflib
from collections.abc import Generator, Hashable, Mapping
from enum import Enum
from types import UnionType
from typing import Optional, TypeVar, Union, get_args, get_origin

from typing_extensions import TypeForm

import numpy as np
import pandas as pd
from pydantic import BaseModel, TypeAdapter

from opengsync_db.categories.ExtendedEnum import DBEnum


def json_encapsulate(key: str, value: str | bytes) -> bytes:
    return b'{"' + key.encode() + b'": ' + (value if isinstance(value, bytes) else value.encode()) + b'}'


def check_string(val: str | None, allowed_special_characters: list[str] | tuple[str, ...] = ("-", "_", "."), required: bool = True) -> str | None:
    """Check if the given string is a valid name.

    Args:
        val (str): The string to check.
        allowed_special_characters (list[str], optional): Defaults to ["-", "_"].

    Returns:
        str | None: Returns None if the string is valid, otherwise returns an error message.
    """
    if pd.isna(val):  # type: ignore
        if not required:
            return None
        return "Value is missing."
    
    allowed_characters = string.ascii_letters + string.digits + "".join(allowed_special_characters)
    
    for c in val:  # type: ignore
        if c not in allowed_characters:
            return "Invalid character in name: '" + c + f"'. You can only use letters, digits and the following special characters: {allowed_special_characters}"
        
    return None


def titlecase_with_acronyms(val: str) -> str:
    return " ".join([c[0].upper() + c[1:] for c in val.split(" ")])


def make_filenameable(val, keep: list[str] | tuple[str, ...] = ('-', '.', '_')) -> str:
    return "".join(c for c in str(val) if c.isalnum() or c in keep)


def make_alpha_numeric(val: str | None, keep: list[str] | tuple[str, ...] = (".", "-", "_"), replace_white_spaces_with: str | None = "_") -> str | None:
    if pd.isna(val) or not val:  # type: ignore
        return None
    
    if replace_white_spaces_with is not None:
        val = val.strip().replace(" ", replace_white_spaces_with)

    if "-" not in keep:
        val = val.replace("-", "_")
    
    val = "".join(c for c in val if c.isalnum() or c in keep)
    val = re.sub(r"_+", "_", val)
    return val 


def parse_float(val: Union[int, float, str, None]) -> float | None:
    if isinstance(val, int) or isinstance(val, float):  # type: ignore
        return float(val)
    if isinstance(val, str):
        try:
            return float("".join(c for c in val if c.isnumeric() or c == "." or c == "-"))
        except ValueError:
            return None
    return None


def parse_int(val: Union[int, str, None]) -> int | None:
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        try:
            return int("".join(c for c in val if c.isnumeric() or c == "-"))
        except ValueError:
            return None
    return None


T = TypeVar('T')
M = TypeVar('M', bound=BaseModel)
I = TypeVar('I', default=Hashable)


def mapstr(
    word: str, tuples: list[tuple[str, T]], cutoff: float = 0.5,
    cap_sensitive: bool = False, filter_non_alphanumeric: bool = True,
) -> T | None:
    
    if pd.isna(word):
        return None

    if not cap_sensitive:
        tuples = [(k.lower(), v) for k, v in tuples]

    if filter_non_alphanumeric:
        tuples = [("".join(c for c in k if c.isalnum()), v) for k, v in tuples]

    tuples = [(k.replace(" ", "").replace("_", "").replace("-", ""), v) for k, v in tuples]

    tt = dict(tuples)

    matches = difflib.get_close_matches(word, tt.keys(), n=1, cutoff=cutoff)
    if (match := next(iter(matches), None)) is None:
        return None

    return tt[match]


def connect_similar_strings(
    refs: list[tuple[str, str]], data: list[str],
    similars: Optional[dict[str, str | int]] = None, cutoff: float = 0.5
) -> dict:
    search_dict = dict([(val.lower().replace(" ", "").replace("_", "").replace("-", ""), key) for key, val in refs])

    res = []
    for word in data:
        _word = word.lower().replace(" ", "").replace("_", "").replace("-", "")
        if similars is not None and _word in similars.keys():
            res.append((similars[_word], 1.0))
        else:
            closest_match = difflib.get_close_matches(word, search_dict.keys(), n=1, cutoff=cutoff)
            if len(closest_match) == 0:
                res.append(None)
            else:
                score = difflib.SequenceMatcher(None, word, closest_match[0]).ratio()
                res.append((search_dict[closest_match[0]], score))

    _data = dict(zip(data, res))
    bests = {}
    for key, val in _data.items():
        if val is None:
            continue
        
        if val[0] in bests.keys():
            if val[1] > bests[val[0]][1]:
                bests[val[0]] = (key, val[1])
        else:
            bests[val[0]] = (key, val[1])

    res = {}
    for key, val in _data.items():
        if val is None:
            res[key] = None
            continue

        if val[0] in bests.keys():
            if bests[val[0]][0] == key:
                res[key] = val[0]
            else:
                res[key] = None
    return res

def get_nameid_column(df: pd.DataFrame, name_col: str, id_col: str, sep: str = "@") -> list[str]:
    return (df[name_col] + sep + df[id_col].astype(str)).tolist()  # type: ignore

def parse_nameid_column(df: pd.DataFrame, col: str, sep: str = "@") -> list[int | None]:
    return df[col].apply(lambda x: int(x.split(sep)[-1]) if pd.notna(x) else None).tolist()

def map_columns(dst: pd.DataFrame, src: pd.DataFrame, idx_columns: list[str] | str | None, col: str) -> pd.Series:
    if idx_columns is not None:
        src = src.set_index(idx_columns)

    mapping = src[col].to_dict()
    if isinstance(idx_columns, str):
        return pd.Series(dst[idx_columns].apply(lambda x: mapping.get(x, None) if pd.notna(x) else None))
    return pd.Series(dst[idx_columns].apply(lambda row: mapping.get(tuple(row), None) if isinstance(row, pd.Series) else mapping.get(row), axis=1))

def normalize_to_ascii(text: str, allow_special_characters: list[str] | tuple[str, ...] = ("_", ".", "-")) -> str:
    GREEK_TO_ASCII = {
        'α': 'a', 'β': 'b', 'γ': 'g', 'δ': 'd', 'ε': 'e', 'ζ': 'z',
        'η': 'h', 'θ': 'th', 'ι': 'i', 'κ': 'k', 'λ': 'l', 'μ': 'm',
        'ν': 'n', 'ξ': 'x', 'ο': 'o', 'π': 'p', 'ρ': 'r', 'σ': 's',
        'ς': 's', 'τ': 't', 'υ': 'y', 'φ': 'f', 'χ': 'ch', 'ψ': 'ps',
        'ω': 'o',
        'Α': 'A', 'Β': 'B', 'Γ': 'G', 'Δ': 'D', 'Ε': 'E', 'Ζ': 'Z',
        'Η': 'H', 'Θ': 'Th', 'Ι': 'I', 'Κ': 'K', 'Λ': 'L', 'Μ': 'M',
        'Ν': 'N', 'Ξ': 'X', 'Ο': 'O', 'Π': 'P', 'Ρ': 'R', 'Σ': 'S',
        'Τ': 'T', 'Υ': 'Y', 'Φ': 'F', 'Χ': 'Ch', 'Ψ': 'Ps', 'Ω': 'O'
    }
    text = "".join(GREEK_TO_ASCII.get(char, char) for char in text)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    if ' ' not in allow_special_characters:
        text = text.replace(' ', '_')
    allowed_pattern = re.escape("".join(allow_special_characters))
    text = re.sub(rf"[^a-zA-Z0-9 {allowed_pattern}]", '', text)
    return text


def filter_subpaths(paths: list[str]) -> list[str]:
    """
    Filter out paths that are subpaths of other paths in the list.
    
    Args:
        paths: List of file/directory paths as strings
    
    Returns:
        List of paths where no path is a subpath of another
    """
    sorted_paths = sorted(paths, key=len, reverse=False)
    filtered_paths = []
    
    for path in sorted_paths:
        normalized_path = path.rstrip('/') + '/'
        
        is_subpath = False
        for existing_path in filtered_paths:
            normalized_existing = existing_path.rstrip('/') + '/'
            if normalized_path.startswith(normalized_existing):
                is_subpath = True
                break
        
        if not is_subpath:
            filtered_paths.append(path)
    
    return filtered_paths


def replace_substrings(text: str, substrings: dict[str, str]) -> str:
    _sorted_substrings = sorted(substrings.items(), key=lambda x: len(x[0]), reverse=True)
    for k, v in _sorted_substrings:
        text = text.replace(k, v)
    return text


def to_json(df: pd.DataFrame) -> str:
    df = df.copy()
    
    for col in df.select_dtypes(include=["object"]):
        df[col] = df[col].apply(lambda x: f"{x.__class__.__name__}${x.id}" if isinstance(x, DBEnum) else x)

    df = df.replace({pd.NA: None, float('nan'): None})
    return json.dumps(df.to_dict(orient="list"))


def is_valid_email(email: str | None) -> bool:
    if pd.isna(email) or not email:  # type: ignore
        return False
    # basic check for email validity
    return "@" in email and "." in email.split("@")[-1]


def _unwrap_numpy_scalar(val: object) -> object:
    """Convert numpy scalars and 0-d arrays to native Python types."""
    if isinstance(val, np.generic) or (isinstance(val, np.ndarray) and val.ndim == 0):
        return val.item()
    return val

def is_missing(val: object) -> bool:
    """True only for scalar NA (None, NaN, NaT, pd.NA). Lists and arrays are never missing."""
    if not pd.api.types.is_scalar(val):
        return False
    missing = pd.isna(val)
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


def _is_enum_annotation(annotation: object) -> bool:
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        args = [a for a in get_args(annotation) if a is not type(None)]
        return len(args) == 1 and _is_enum_annotation(args[0])
    return isinstance(annotation, type) and issubclass(annotation, Enum)


def _cell_value(row: Mapping[str, object] | pd.Series, col: object) -> object:
    val = _unwrap_numpy_scalar(row[col])  # type: ignore[index]
    return None if is_missing(val) else val


def validate_row(row: Mapping[str, object] | pd.Series, model: type[M]) -> M:
    """Validate a mapping or Series against a Pydantic model.

    Only keys matching ``model`` fields are included. NaN/NaT values
    are converted to ``None``, and numpy scalars are unwrapped to
    native Python types before validation.

    Fields without a default must be present. Fields with a default
    (``bonus: int = 0``, ``note: str | None = None``) are optional
    columns and are filled in when absent::

        class User(BaseModel):
            id: int
            score: float | None
            bonus: int = 0

    If ``model`` declares a private ``_raw_`` attribute, leftover
    keys that are not model fields are stored there as a dict.

    Raises:
        pydantic.ValidationError: If the row fails validation or a
            required column is missing.
    """
    data: dict[str, object] = {}
    for col in model.model_fields:
        if col not in row:
            continue
        data[col] = _cell_value(row, col)
    instance = model.model_validate(data)
    if "_raw_" in model.__private_attributes__:
        model_fields = model.model_fields
        instance._raw_ = {  # type: ignore[attr-defined]
            col: _cell_value(row, col)
            for col in row.keys()
            if col not in model_fields and col != "_raw_"
        }
    return instance


def validate(df: pd.DataFrame, model: type[M]) -> pd.DataFrame:
    """Validate a DataFrame against a Pydantic model and return a DataFrame of dumped rows.

    Enum fields (including ``IntEnum`` / ``ExtendedEnum``) are kept as
    enum members, not converted to ints.

    Raises:
        pydantic.ValidationError: Immediately on the first row that fails
            validation.
    """
    columns = list(model.model_fields.keys())
    data: dict[str, list[object]] = {name: [] for name in columns}
    for _, row in df.iterrows():
        instance = validate_row(row, model)
        for name in columns:
            data[name].append(getattr(instance, name))

    return pd.DataFrame({
        name: (
            pd.Series(values, dtype="object")
            if _is_enum_annotation(model.model_fields[name].annotation)
            else values
        )
        for name, values in data.items()
    })


def safe_iter(
    df: pd.DataFrame,
    model: type[M],
    index_type: type[I] = Hashable,
) -> Generator[tuple[I, M], None, None]:
    """Iterate over DataFrame rows, validating each against a Pydantic model.

    For each row, only columns matching ``model`` fields are included.
    NaN/NaT values are converted to ``None``, and numpy scalars are
    unwrapped to native Python types before validation.

    If ``model`` declares a private ``_raw_`` attribute, remaining
    DataFrame columns that are not model fields are stored there.

    Args:
        df: Source DataFrame.
        model: Pydantic model class to validate each row against.
        index_type: Expected type of the DataFrame index. Defaults to
            ``Hashable`` (no validation). Pass ``int`` or ``str`` to
            validate each index value with Pydantic's ``TypeAdapter``.

    Yields:
        Tuples of ``(index, model_instance)`` where ``index`` is the
        DataFrame row index (validated if ``index_type`` is specified)
        and ``model_instance`` is the validated Pydantic model.

    Raises:
        pydantic.ValidationError: Immediately on the first row or index
            that fails validation.
    """
    _validate_index = index_type is not Hashable
    if _validate_index:
        index_adapter = TypeAdapter(index_type)

    for idx, row in df.iterrows():
        if _validate_index:
            idx = index_adapter.validate_python(idx)  # type: ignore[assignment]
        yield idx, validate_row(row, model)  # type: ignore[return-value]


def safe_deduplicated(df: pd.DataFrame, model: type[M]) -> list[M]:
    """Return unique combinations of ``model`` fields as validated instances.

    Column names are taken from ``model`` field names. Duplicate rows
    are collapsed with :meth:`pandas.DataFrame.drop_duplicates` (a
    single-field model is just unique values of that column), then each
    remaining row is validated through ``model``::

        class Schema(BaseModel):
            number: int
            text: str | None

        rows: list[Schema] = parsing.safe_deduplicated(df, Schema)

    Args:
        df: Source DataFrame.
        model: Pydantic model class whose fields define the columns
            to consider. Each unique combination is validated against
            this model.

    Returns:
        A list of validated ``model`` instances, one per unique
        combination, in first-seen order.

    Raises:
        pydantic.ValidationError: Immediately on the first unique row
            that fails validation.
    """
    cols = list(model.model_fields)
    unique_df = df.loc[:, cols].drop_duplicates()
    return [validate_row(row, model) for _, row in unique_df.iterrows()]


def safe_unique(df: pd.DataFrame, col: str, _type: TypeForm[T]) -> list[T]:
    """Return unique values of ``col``, validated as ``_type``.

    Missing values (``NaN``, ``NaT``, ``pd.NA``) are converted to
    ``None`` before validation. Pass an optional type when the column
    may contain empties::

        names: list[str] = parsing.safe_unique(df, "name", str)
        ids: list[int | None] = parsing.safe_unique(df, "id", int | None)

    Duplicate values are collapsed in first-seen order. A non-optional
    ``_type`` raises if the column contains missing values.

    Raises:
        pydantic.ValidationError: Immediately on the first unique value
            that fails validation.
    """
    adapter = TypeAdapter(_type)
    result: list[T] = []
    seen: set[object] = set()
    for val in df[col].unique():
        raw = _unwrap_numpy_scalar(val)
        if is_missing(raw):
            raw = None
        validated = adapter.validate_python(raw)
        if validated in seen:
            continue
        seen.add(validated)
        result.append(validated)
    return result


def safe_groupby(
    df: pd.DataFrame,
    key_model: type[M],
    sort: bool = False,
    dropna: bool = False,
) -> Generator[tuple[M, pd.DataFrame], None, None]:
    """Group DataFrame rows by ``key_model`` fields, validating each group key.

    Works like :func:`pandas.DataFrame.groupby`, but the grouping columns
    are taken from ``key_model`` field names and each group key is
    validated through that model.  The group DataFrame is returned
    unchanged.

    Args:
        df: Source DataFrame.
        key_model: Pydantic model class whose field names are used as
            grouping columns.  Each group key is validated against this
            model.

    Yields:
        Tuples of ``(key, group_df)`` where ``key`` is the validated
        Pydantic model instance and ``group_df`` is the raw subset
        DataFrame for that group.

    Raises:
        pydantic.ValidationError: Immediately on the first group key that
            fails validation.
    """
    by_cols = list(key_model.model_fields)
    by = by_cols[0] if len(by_cols) == 1 else by_cols

    for group_key, group_df in df.groupby(by, sort=sort, dropna=dropna):
        if isinstance(group_key, tuple):
            raw_key = dict(zip(by_cols, group_key))
        else:
            raw_key = {by_cols[0]: group_key}

        yield validate_row(raw_key, key_model), group_df
