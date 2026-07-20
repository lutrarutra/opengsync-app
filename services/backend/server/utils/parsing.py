import string
import re
import json
import unicodedata
import difflib
from collections.abc import Generator, Hashable
from typing import Union, TypeVar, Optional

import pandas as pd
from pydantic import BaseModel, TypeAdapter

from opengsync_db.categories.ExtendedEnum import DBEnum


def json_encapsulate(key: str, value: str | bytes) -> bytes:
    return b'{"' + key.encode() + b'": ' + (value if isinstance(value, bytes) else value.encode()) + b'}'


def check_string(val: str | None, allowed_special_characters: list[str] = ["-", "_", "."], required: bool = True) -> str | None:
    """Check if the given string is a valid name.

    Args:
        val (str): The string to check.
        allowed_special_characters (list[str], optional): Defaults to ["-", "_"].

    Returns:
        str | None: Returns None if the string is valid, otherwise returns an error message.
    """
    if pd.isna(val):
        if not required:
            return None
        return "Value is missing."
    
    allowed_characters = string.ascii_letters + string.digits + "".join(allowed_special_characters)
    
    for c in val:
        if c not in allowed_characters:
            return "Invalid character in name: '" + c + f"'. You can only use letters, digits and the following special characters: {allowed_special_characters}"
        
    return None


def titlecase_with_acronyms(val: str) -> str:
    return " ".join([c[0].upper() + c[1:] for c in val.split(" ")])


def make_filenameable(val, keep: list[str] = ['-', '.', '_']) -> str:
    return "".join(c for c in str(val) if c.isalnum() or c in keep)


def make_alpha_numeric(val: str | None, keep: list[str] = [".", "-", "_"], replace_white_spaces_with: str | None = "_") -> str | None:
    if pd.isna(val) or not val:
        return None
    
    if replace_white_spaces_with is not None:
        val = val.strip().replace(" ", replace_white_spaces_with)

    if "-" not in keep:
        val = val.replace("-", "_")
    
    val = "".join(c for c in val if c.isalnum() or c in keep)
    val = re.sub(r"_+", "_", val)
    return val 


def parse_float(val: Union[int, float, str, None]) -> float | None:
    if isinstance(val, int) or isinstance(val, float):
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

def normalize_to_ascii(text: str, allow_special_characters: list[str] = ["_", ".", "-"]) -> str:
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
    if pd.isna(email) or not email:
        return False
    # basic check for email validity
    return "@" in email and "." in email.split("@")[-1]


def safe_iter(
    df: pd.DataFrame,
    model: type[M],
    index_type: type[I] = Hashable,
) -> Generator[tuple[I, M], None, None]:
    """Iterate over DataFrame rows, validating each against a Pydantic model.

    For each row, only columns matching ``model`` fields are included.
    NaN/NaT values are converted to ``None``, and numpy scalars are
    unwrapped to native Python types before validation.

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
    model_fields = set(model.model_fields.keys())
    columns = [col for col in df.columns if col in model_fields]

    _validate_index = index_type is not Hashable
    if _validate_index:
        index_adapter = TypeAdapter(index_type)

    for idx, row in df.iterrows():
        if _validate_index:
            idx = index_adapter.validate_python(idx)  # type: ignore[assignment]

        row_dict: dict[str, object] = {}
        for col in columns:
            val = row[col]
            if pd.isna(val):
                row_dict[col] = None
            elif hasattr(val, 'item'):
                row_dict[col] = val.item()  # type: ignore[union-attr]
            else:
                row_dict[col] = val

        yield idx, model.model_validate(row_dict)  # type: ignore[return-type]


def safe_groupby(
    df: pd.DataFrame,
    by: str | list[str],
    key_model: type[M],
) -> Generator[tuple[M, pd.DataFrame], None, None]:
    """Group DataFrame rows by column(s), validating the group key against a Pydantic model.

    Works like :func:`pandas.DataFrame.groupby`, but the group key is
    validated through ``key_model``.  The group DataFrame is returned
    unchanged.

    Args:
        df: Source DataFrame.
        by: Column name(s) to group by (passed to ``df.groupby(by)``).
        key_model: Pydantic model class to validate each group key against.
            The model's field names must match the ``by`` column names.

    Yields:
        Tuples of ``(key, group_df)`` where ``key`` is the validated
        Pydantic model instance and ``group_df`` is the raw subset
        DataFrame for that group.

    Raises:
        pydantic.ValidationError: Immediately on the first group key that
            fails validation.
    """
    by_cols = [by] if isinstance(by, str) else by

    for group_key, group_df in df.groupby(by):
        if isinstance(group_key, tuple):
            key_dict = dict(zip(by_cols, group_key))
        else:
            key_dict = {by_cols[0]: group_key}

        yield key_model.model_validate(key_dict), group_df
