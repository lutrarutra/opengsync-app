from typing import Optional, Union, TypeVar
import difflib
import string

import pandas as pd
import scipy
import numpy as np

from .. import logger

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


# def _hamming_distance_shared_bases(seq1: str, seq2: str) -> int:
#     """Calculate Hamming distance using only matching positions (shortest shared length)."""
#     min_len = min(len(seq1), len(seq2))
#     return sum(c1 != c2 for c1, c2 in zip(seq1[:min_len], seq2[:min_len]))


# def min_hamming_distances(seq_list: list[str]) -> list[int]:
#     distances = []
#     for i, ref in enumerate(seq_list):
#         other_seqs = seq_list[:i] + seq_list[i + 1:]
#         distances.append(min(_hamming_distance_shared_bases(ref, other) for other in other_seqs))
#     return distances


def check_indices(df: pd.DataFrame, groupby: Optional[str] = None) -> pd.DataFrame:
    df["error"] = None
    df["warning"] = None

    indices = ["sequence_i7"]
    if "sequence_i5" in df.columns and not df["sequence_i5"].isna().all():
        indices.append("sequence_i5")

    df["combined_index"] = ""
    for index in indices:
        df[index] = df[index].apply(lambda x: x.strip() if pd.notna(x) else "")
        _max = int(df[index].str.len().max())
        df["combined_index"] += df[index].apply(lambda x: x + " " * (_max - len(x)) if pd.notna(x) else "")
        
    if len(df) > 1:
        if "sequence_i5" in df.columns:
            same_barcode_in_different_indices = df["sequence_i7"] == df["sequence_i5"]
            df.loc[same_barcode_in_different_indices, "warning"] = "Same barcode in different indices"

        df["min_hamming_dist"] = None
        df["min_idx"] = None

        def hamming(x, y):
            return scipy.spatial.distance.hamming(list(x[0]), list(y[0]))
        
        if groupby is None:
            _max = int(df["combined_index"].str.len().max())
            df["combined_index"] = df["combined_index"].apply(lambda x: x + " " * (_max - len(x)) if pd.notna(x) else "")
            a = np.array(df["combined_index"]).reshape(-1, 1)
            dists = scipy.spatial.distance.pdist(a, lambda x, y: hamming(x, y))
            p_dist = scipy.spatial.distance.squareform(dists)
            np.fill_diagonal(p_dist, np.nan)
            min_idx = np.nanargmin(p_dist, axis=0)
            df["min_idx"] = min_idx
            df["min_hamming_dist"] = p_dist[np.arange(p_dist.shape[0]), min_idx]
        else:
            for _, _df in df.groupby(groupby):
                if len(_df) > 1:
                    _max = int(df["combined_index"].str.len().max())
                    _df["combined_index"] = _df["combined_index"].apply(lambda x: x + " " * (_max - len(x)) if pd.notna(x) else "")

                    a = np.array(_df["combined_index"]).reshape(-1, 1)

                    dists = scipy.spatial.distance.pdist(a, lambda x, y: hamming(x, y))
                    p_dist = scipy.spatial.distance.squareform(dists)
                    np.fill_diagonal(p_dist, np.nan)
                    min_idx = np.nanargmin(p_dist, axis=0)
                    df.loc[_df.index, "min_idx"] = min_idx
                    df.loc[_df.index, "min_hamming_dist"] = p_dist[np.arange(p_dist.shape[0]), min_idx]
                else:
                    df.loc[_df.index, "min_idx"] = 0
                    df.loc[_df.index, "min_hamming_dist"] = 1.0
    else:
        df["min_hamming_dist"] = 1.0
        df["min_idx"] = 0

    df["min_hamming_bases"] = df["min_hamming_dist"] * df["combined_index"].apply(lambda x: len(x))
    df["min_hamming_bases"] = df["min_hamming_bases"].astype(int)

    df.loc[df["min_hamming_bases"] < 1, "error"] = "Hamming distance of 0 between barcode combination in two or more libraries on same lane."
    df.loc[df["min_hamming_bases"] < 3, "warning"] = "Small hamming distance between barcode combination in two or more libraries on same lane."

    return df


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
