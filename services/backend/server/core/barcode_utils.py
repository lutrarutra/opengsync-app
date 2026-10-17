"""Pure pandas utilities for checking barcode clashes.

Ported from packages/opengsync-server/opengsync_server/tools/utils.py
with no Flask/SQLAlchemy dependencies.
"""



from typing import Literal, Sequence

import pandas as pd


def reverse_complement(seq: str | None) -> str:
    if pd.isna(seq):
        return ""
    complement = {"A": "T", "T": "A", "C": "G", "G": "C", "N": "N", "+": "+"}
    return "".join(complement.get(base, base) for base in reversed(seq))


def _hamming_distance_shared_bases(seq1: str, seq2: str) -> int:
    """Calculate Hamming distance using only matching positions (shortest shared length)."""
    min_len = min(len(seq1), len(seq2))
    return sum(c1 != c2 and c1 != "N" and c2 != "N" for c1, c2 in zip(seq1[:min_len], seq2[:min_len]))


def min_hamming_distances(
    seq_list: list[str], rc: Literal["i7", "i5", "both", "i7i5"] | None = None
) -> list[int]:
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
        other_seqs = seq_list[:i] + seq_list[i + 1 :]
        distances.append(min(_hamming_distance_shared_bases(ref, other) for other in other_seqs))
    return distances


def _get_combined_index(df: pd.DataFrame, indices: list[str]) -> pd.Series:
    combined_index = pd.Series([""] * len(df), index=df.index, dtype="string")
    for index in indices:
        df[index] = df[index].apply(lambda x: x.strip() if pd.notna(x) else "")
        _max = int(df[index].str.len().max())
        combined_index += "+" + df[index].str.ljust(_max, "N")
    return combined_index.str.lstrip("+")


def _check_indices(
    df: pd.DataFrame,
    indices: list[str],
    groupby: str | list[str] | None = None,
    rc: Literal["i7", "i5", "both", "i7i5"] | None = None,
) -> pd.DataFrame:
    df["combined_index"] = ""
    df["min_hamming_bases"] = None

    if len(df) > 1:
        if groupby is None:
            df["combined_index"] = _get_combined_index(df, indices)
            if "sequence_i5" in df.columns:
                same_barcode_in_different_indices = df["sequence_i7"] == df["sequence_i5"]
                df.loc[same_barcode_in_different_indices, "warning"] = "Same barcode in different indices"

            df["min_hamming_bases"] = df["combined_index"].apply(lambda x: len(x) - x.count("N") - x.count("+")).min()
            df["min_hamming_bases"] = min_hamming_distances(df["combined_index"].tolist(), rc=rc)
        else:
            for _, _df in df.groupby(groupby):
                _df["combined_index"] = _get_combined_index(_df, indices)
                if "sequence_i5" in _df.columns:
                    same_barcode_in_different_indices = _df["sequence_i7"] == _df["sequence_i5"]
                    _df.loc[same_barcode_in_different_indices, "warning"] = "Same barcode in i7 & i5 indices"

                if len(_df) < 2:
                    _df["min_hamming_bases"] = _df["combined_index"].apply(
                        lambda x: len(x) - x.count("N") - x.count("+")
                    ).min()
                else:
                    _df["min_hamming_bases"] = min_hamming_distances(_df["combined_index"].tolist(), rc=rc)

                df.loc[_df.index, "combined_index"] = _df["combined_index"]
                df.loc[_df.index, "min_hamming_bases"] = _df["min_hamming_bases"]
    elif len(df) == 1:
        df["combined_index"] = _get_combined_index(df, indices)
        df["min_hamming_bases"] = df["combined_index"].apply(lambda x: len(x) - x.count("N") - x.count("+")).min()
    else:
        df["combined_index"] = ""
        df["min_hamming_bases"] = None

    return df


def check_indices(df: pd.DataFrame, groupby: str | list[str] | None = None) -> pd.DataFrame:
    """Annotate a barcode DataFrame with error/warning flags and hamming distances.

    Expects columns: ``sequence_i7``, optionally ``sequence_i5``, ``kit_i7_id``, ``kit_i5_id``, ``index_type_id``.
    Adds columns: ``combined_index``, ``min_hamming_bases``, ``error``, ``warning``, and RC distance columns.
    """
    df = df.copy()
    df["error"] = None
    df["warning"] = None

    indices = ["sequence_i7"]
    if "sequence_i5" in df.columns and not df["sequence_i5"].isna().all():
        indices.append("sequence_i5")

    df = _check_indices(df, indices=indices, groupby=groupby)

    df["rc_i7_min_hamming_bases"] = _check_indices(df.copy(), indices=indices, groupby=groupby, rc="i7")["min_hamming_bases"]

    if "sequence_i5" in df.columns:
        df["rc_i5_min_hamming_bases"] = _check_indices(df.copy(), indices=indices, groupby=groupby, rc="i5")["min_hamming_bases"]
        df["rc_min_hamming_bases"] = _check_indices(df.copy(), indices=indices, groupby=groupby, rc="both")["min_hamming_bases"]
        df["rc_i7i5_min_hamming_bases"] = _check_indices(df.copy(), indices=indices, groupby=groupby, rc="i7i5")["min_hamming_bases"]

    df.loc[df["min_hamming_bases"] < 1, "error"] = "Hamming distance of 0 between barcode combination in two or more libraries."
    df.loc[df["min_hamming_bases"] < 3, "warning"] = "Small hamming distance between barcode combination in two or more libraries."
    return df