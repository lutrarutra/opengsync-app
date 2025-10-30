from typing import Optional, Union, TypeVar, Sequence, Literal
from pathlib import Path
import itertools
import json
import difflib
import string
import unicodedata
import re

import pandas as pd

from opengsync_db import models, exceptions, DBHandler, categories
from opengsync_db.categories.ExtendedEnum import DBEnum

from .. import logger
from .WeekTimeWindow import WeekTimeWindow

tab_10_colors = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf"
]


def to_identifier(n: int) -> str:
    out = ""

    while n >= 0:
        n, r = divmod(n, 26)
        out = string.ascii_uppercase[r] + out
        n -= 1

    return out

def reverse_complement(seq: str | None) -> str:
    if pd.isna(seq):
        return ""
    complement = {"A": "T", "T": "A", "C": "G", "G": "C", "N": "N", "+": "+"}
    return "".join(complement.get(base, base) for base in reversed(seq))

def _hamming_distance_shared_bases(seq1: str, seq2: str) -> int:
    """Calculate Hamming distance using only matching positions (shortest shared length)."""
    min_len = min(len(seq1), len(seq2))
    return sum(c1 != c2 and c1 != 'N' and c2 != 'N' for c1, c2 in zip(seq1[:min_len], seq2[:min_len]))


def min_hamming_distances(seq_list: list[str], rc: Literal["i7", "i5", "both", "i7i5"] | None = None) -> list[int]:
    distances = []
    for i, ref in enumerate(seq_list):
        match rc:
            case "i7":
                ref_i7, ref_i5 = ref.split("+") if "+" in ref else (ref, "")
                ref = reverse_complement(ref_i7) + "+" + ref_i5
            case "i5":
                ref_i7, ref_i5 = ref.split("+") if "+" in ref else (ref, "")
                ref = ref_i7 + "+" + reverse_complement(ref_i5)
            case "both":
                ref = reverse_complement(ref)
            case "i7i5":
                ref_i7, ref_i5 = ref.split("+") if "+" in ref else (ref, "")
                ref = reverse_complement(ref_i7) + "+" + reverse_complement(ref_i5)
            case _:
                pass
        other_seqs = seq_list[:i] + seq_list[i + 1:]
        distances.append(min(_hamming_distance_shared_bases(ref, other) for other in other_seqs))
    return distances


def __get_combined_index(df: pd.DataFrame, indices: list[str]) -> pd.Series:
    combined_index = pd.Series([""] * len(df), index=df.index, dtype="string")
    for index in indices:
        df[index] = df[index].apply(lambda x: x.strip() if pd.notna(x) else "")
        _max = int(df[index].str.len().max())
        combined_index += "+" + df[index].str.ljust(_max, "N")

    return combined_index.str.lstrip("+")


def __check_indices(df: pd.DataFrame, indices: list[str], groupby: str | list[str] | None = None, rc: Literal["i7", "i5", "both", "i7i5"] | None = None) -> pd.DataFrame:
    df["combined_index"] = ""
    df["min_hamming_bases"] = None

    if len(df) > 1:
        if groupby is None:
            df["combined_index"] = __get_combined_index(df, indices)     
            if "sequence_i5" in df.columns:
                same_barcode_in_different_indices = df["sequence_i7"] == df["sequence_i5"]
                df.loc[same_barcode_in_different_indices, "warning"] = "Same barcode in different indices"
            
            df["min_hamming_bases"] = df["combined_index"].apply(lambda x: len(x) - x.count("N") - x.count("+")).min()
            df["min_hamming_bases"] = min_hamming_distances(df["combined_index"].tolist(), rc=rc)
        else:
            for _, _df in df.groupby(groupby):             
                _df["combined_index"] = __get_combined_index(_df, indices)
                if "sequence_i5" in _df.columns:
                    same_barcode_in_different_indices = _df["sequence_i7"] == _df["sequence_i5"]
                    _df.loc[same_barcode_in_different_indices, "warning"] = "Same barcode in i7 & i5 indices"

                if len(_df) < 2:
                    _df["min_hamming_bases"] = _df["combined_index"].apply(lambda x: len(x) - x.count("N") - x.count("+")).min()
                else:
                    _df["min_hamming_bases"] = min_hamming_distances(_df["combined_index"].tolist(), rc=rc)
                
                df.loc[_df.index, "combined_index"] = _df["combined_index"]
                df.loc[_df.index, "min_hamming_bases"] = _df["min_hamming_bases"]
    elif len(df) == 1:
        df["combined_index"] = __get_combined_index(df, indices)
        df["min_hamming_bases"] = df["combined_index"].apply(lambda x: len(x) - x.count("N") - x.count("+")).min()
    else:
        df["combined_index"] = ""
        df["min_hamming_bases"] = None
        
    return df


def check_indices(df: pd.DataFrame, groupby: str | list[str] | None = None) -> pd.DataFrame:
    df = df.copy()
    df["error"] = None
    df["warning"] = None

    indices = ["sequence_i7"]
    if "sequence_i5" in df.columns and not df["sequence_i5"].isna().all():
        indices.append("sequence_i5")

    df = __check_indices(df, indices=indices, groupby=groupby)

    df["rc_i7_min_hamming_bases"] = __check_indices(df.copy(), indices=indices, groupby=groupby, rc="i7")["min_hamming_bases"]
    
    if "sequence_i5" in df.columns:
        df["rc_i5_min_hamming_bases"] = __check_indices(df.copy(), indices=indices, groupby=groupby, rc="i5")["min_hamming_bases"]
        df["rc_min_hamming_bases"] = __check_indices(df.copy(), indices=indices, groupby=groupby, rc="both")["min_hamming_bases"]
        df["rc_i7i5_min_hamming_bases"] = __check_indices(df.copy(), indices=indices, groupby=groupby, rc="i7i5")["min_hamming_bases"]

    df.loc[df["min_hamming_bases"] < 1, "error"] = "Hamming distance of 0 between barcode combination in two or more libraries."
    df.loc[df["min_hamming_bases"] < 3, "warning"] = "Small hamming distance between barcode combination in two or more libraries."
    return df


def parse_time_windows(data: list[dict]) -> list[WeekTimeWindow]:
    from datetime import time
    windows = []
    for entry in data:
        weekday = entry["weekday"]
        start_time = entry["start_time"]
        end_time = entry["end_time"]
        
        try:
            weekday = int(weekday)
        except ValueError:
            raise ValueError(f"'{weekday}' is not a valid weekday number (0=Monday,.., 6=Sunday).")
        
        try:
            start_time = time.fromisoformat(start_time)
        except ValueError:
            raise ValueError(f"'{start_time}' is not a valid time in HH:MM format.")
        
        try:
            end_time = time.fromisoformat(end_time)
        except ValueError:
            raise ValueError(f"'{end_time}' is not a valid time in HH:MM format.")
        
        windows.append(WeekTimeWindow(weekday, start_time, end_time))
    return windows


def check_string(val: str | None, allowed_special_characters: list[str] = ["-", "_"], required: bool = True) -> str | None:
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


def make_alpha_numeric(val, keep: list[str] = [".", "-", "_"], replace_white_spaces_with: Optional[str] = "_") -> str | None:
    if pd.isna(val) or val is None or val == "":
        return None
    
    if replace_white_spaces_with is not None:
        val = val.strip().replace(" ", replace_white_spaces_with)
    return "".join(c for c in val if c.isalnum() or c in keep)
    

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


def get_barcode_table(db: DBHandler, libraries: Sequence[models.Library]) -> pd.DataFrame:
    library_data = {
        "library_id": [],
        "library_name": [],
        "library_type_id": [],
        "pool": [],
        "index_well": [],
        "kit_i7": [],
        "name_i7": [],
        "sequence_i7": [],
        "kit_i5": [],
        "name_i5": [],
        "sequence_i5": [],
        "index_type_id": [],
    }
    
    for library in libraries:
        library_data["index_type_id"].append(library.index_type_id)
        library_data["library_id"].append(library.id)
        library_data["library_name"].append(library.name)
        library_data["library_type_id"].append(library.type.id)
        library_data["pool"].append(library.pool.name if library.pool else None)

        if len(library.indices) == 0:
            library_data["index_well"].append(None)
            library_data["kit_i7"].append(None)
            library_data["name_i7"].append(None)
            library_data["sequence_i7"].append(None)
            library_data["kit_i5"].append(None)
            library_data["name_i5"].append(None)
            library_data["sequence_i5"].append(None)

        else:
            kit_i7s = []
            names_i7 = []
            sequences_i7 = []

            for (kit_i7_id, name_i7), seqs_i7 in library.adapters_i7().items():
                if kit_i7_id is not None:
                    if (kit_i7 := db.index_kits.get(kit_i7_id)) is None:
                        logger.error(f"Index kit {kit_i7_id} not found in database")
                        raise exceptions.ElementDoesNotExist("Index kit not found in database")
                    kit_i7 = kit_i7.identifier
                else:
                    kit_i7 = None
                kit_i7s.append(kit_i7 or "")
                names_i7.append(name_i7 or "")
                sequences_i7.append(";".join(seqs_i7) if pd.notna(seqs_i7).any() and seqs_i7 else "")

            kit_i5s = []
            names_i5 = []
            sequences_i5 = []
            for (kit_i5_id, name_i5), seqs_i5 in library.adapters_i5().items():
                if kit_i5_id is not None:
                    if (kit_i5 := db.index_kits.get(kit_i5_id)) is None:
                        logger.error(f"Index kit {kit_i5_id} not found in database")
                        raise exceptions.ElementDoesNotExist("Index kit not found in database")
                    kit_i5 = kit_i5.identifier
                else:
                    kit_i5 = None
                kit_i5s.append(kit_i5 or "")
                names_i5.append(name_i5 or "")
                sequences_i5.append(";".join(seqs_i5))

            library_data["index_well"].append(None)
            library_data["kit_i7"].append(";".join(kit_i7s) if len(kit_i7s) else None)
            library_data["name_i7"].append(";".join(names_i7) if len(names_i7) else None)
            library_data["sequence_i7"].append(";".join(sequences_i7) if len(sequences_i7) else None)
            library_data["kit_i5"].append(";".join(kit_i5s) if len(kit_i5s) else None)
            library_data["name_i5"].append(";".join(names_i5) if len(names_i5) else None)
            library_data["sequence_i5"].append(";".join(sequences_i5) if len(sequences_i5) else None)

    df = pd.DataFrame(library_data)
    df["library_id"] = df["library_id"].astype(int)
    return df


def get_nameid_column(df: pd.DataFrame, name_col: str, id_col: str, sep: str = "@") -> list[str]:
    return (df[name_col] + sep + df[id_col].astype(str)).tolist()


def parse_nameid_column(df: pd.DataFrame, col: str, sep: str = "@") -> list[int | None]:
    return df[col].apply(lambda x: int(x.split(sep)[-1]) if pd.notna(x) else None).tolist()


def map_columns(dst: pd.DataFrame, src: pd.DataFrame, idx_columns: list[str] | str | None, col: str) -> pd.Series:
    if idx_columns is not None:
        src = src.set_index(idx_columns)

    mapping = src[col].to_dict()
    if isinstance(idx_columns, str):
        return pd.Series(dst[idx_columns].apply(lambda x: mapping.get(x, None) if pd.notna(x) else None))
    return pd.Series(dst[idx_columns].apply(lambda row: mapping.get(tuple(row), None) if isinstance(row, pd.Series) else mapping.get(row), axis=1))


def update_index_kits(db: DBHandler, app_data_folder: Path):
    import pandas as pd
    kits_path = app_data_folder / "kits"
    kits_path.mkdir(parents=True, exist_ok=True)

    data = {
        "kit_id": [],
        "kit": [],
        "name": [],
        "sequence": [],
        "well": [],
        "index_type_id": [],
        "barcode_type_id": [],
    }

    def add_barcode(kit_id: int, kit: str, name: str, sequence: str, well: str, index_type_id: int, barcode_type_id: int):
        data["kit_id"].append(kit_id)
        data["kit"].append(kit)
        data["name"].append(name)
        data["sequence"].append(sequence)
        data["well"].append(well)
        data["index_type_id"].append(index_type_id)
        data["barcode_type_id"].append(barcode_type_id)

    for kit in db.index_kits.find(limit=None, sort_by="id", descending=True)[0]:
        df = db.pd.get_index_kit_barcodes(kit.id, per_index=True)
        for _, row in df.iterrows():
            match kit.type:
                case categories.IndexType.DUAL_INDEX:
                    add_barcode(
                        kit_id=kit.id,
                        kit=kit.identifier,
                        name=row["name_i7"],
                        sequence=row["sequence_i7"],
                        well=row["well"],
                        index_type_id=kit.type.id,
                        barcode_type_id=categories.BarcodeType.INDEX_I7.id,
                    )
                    add_barcode(
                        kit_id=kit.id,
                        kit=kit.identifier,
                        name=row["name_i5"],
                        sequence=row["sequence_i5"],
                        well=row["well"],
                        index_type_id=kit.type.id,
                        barcode_type_id=categories.BarcodeType.INDEX_I5.id,
                    )
                case categories.IndexType.COMBINATORIAL_DUAL_INDEX:
                    if pd.notna(row["name_i7"]):
                        add_barcode(
                            kit_id=kit.id,
                            kit=kit.identifier,
                            name=row["name_i7"],
                            sequence=row["sequence_i7"],
                            well=row["well"],
                            index_type_id=kit.type.id,
                            barcode_type_id=categories.BarcodeType.INDEX_I7.id,
                        )
                    if pd.notna(row["name_i5"]):
                        add_barcode(
                            kit_id=kit.id,
                            kit=kit.identifier,
                            name=row["name_i5"],
                            sequence=row["sequence_i5"],
                            well=row["well"],
                            index_type_id=kit.type.id,
                            barcode_type_id=categories.BarcodeType.INDEX_I5.id,
                        )

                case categories.IndexType.SINGLE_INDEX_I7:
                    add_barcode(
                        kit_id=kit.id,
                        kit=kit.identifier,
                        name=row["name_i7"],
                        sequence=row["sequence_i7"],
                        well=row["well"],
                        index_type_id=kit.type.id,
                        barcode_type_id=categories.BarcodeType.INDEX_I7.id,
                    )
                case categories.IndexType.TENX_ATAC_INDEX:
                    for i in range(1, 5):
                        add_barcode(
                            kit_id=kit.id,
                            kit=kit.identifier,
                            name=row["name"],
                            sequence=row[f"sequence_{i}"],
                            well=row["well"],
                            index_type_id=kit.type.id,
                            barcode_type_id=categories.BarcodeType.INDEX_I7.id,
                        )

    pd.DataFrame(data).to_pickle(kits_path / "barcodes.pkl")


def get_index_kit_barcode_map(
    app_data_folder: Path, barcode_types: list[categories.BarcodeTypeEnum] | None = None, index_types: list[categories.IndexTypeEnum] | None = None
) -> pd.DataFrame:
    path = app_data_folder / "kits" / "barcodes.pkl"
    if path.exists() and path.is_file():
        df = pd.read_pickle(path)
        if barcode_types is not None:
            df = df[df["barcode_type_id"].isin([bt.id for bt in barcode_types])]
        if index_types is not None:
            df = df[df["index_type_id"].isin([it.id for it in index_types])]
        return df.reset_index(drop=True)
        
    return pd.DataFrame(columns=["kit_id", "kit", "name", "sequence", "well", "index_type_id"])


def is_browser_friendly(mimetype: str | None) -> bool:
    if not mimetype:
        return False
    return (
        mimetype.startswith("image/") or
        mimetype.startswith("text/") or
        mimetype in {
            "application/pdf",
            "application/javascript",
            "application/json",
        }
    )


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
    for k, v in substrings.items():
        text = text.replace(k, v)
    return text


def check_index_constraints(indices: list[str], must_have_bases: list[str] = ['T', 'C']) -> bool:    
    bases = set([c.upper() for c in must_have_bases])

    if len(indices) == 0:
        raise ValueError("At least one index must be provided")
    
    l = len(indices[0])
    for index in indices:
        if len(index) != l:
            raise ValueError("All indices must have the same length")

    for idx in range(l):
        pass_contstraints = False
        for index in indices:
            if index[idx] in bases:
                pass_contstraints = True
                break
            
        if not pass_contstraints:
            return False
        
    return True


def generate_valid_combinations(
    indices: list[str], additional_indices: list[str], must_have_bases: list[str] = ["C", "T"],
    max_iterations: int = 100_000, max_suggestions: int = 20, min_samples: int | None = None
) -> list[list[str]]:        
    if indices and check_index_constraints(indices, must_have_bases):
        return []
    
    res = []
    i = 0

    for n in range(min_samples or 1, len(additional_indices) + 1):
        for perm in itertools.permutations(additional_indices, n):
            t = indices + list(perm)
            if check_index_constraints(t, must_have_bases):
                res.append(perm)
                if len(res) >= max_suggestions:
                    return res
            i += 1
            if i > max_iterations:
                return res
    
    return res


def to_json(df: pd.DataFrame) -> str:
    df = df.copy()
    
    for col in df.select_dtypes(include=["object"]):
        df[col] = df[col].apply(lambda x: f"{x.__class__.__name__}${x.id}" if isinstance(x, DBEnum) else x)

    df = df.replace({pd.NA: None, float('nan'): None})
    return json.dumps(df.to_dict(orient="list"))
