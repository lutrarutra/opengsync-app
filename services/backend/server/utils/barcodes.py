from typing import Literal, Sequence
import itertools

import pandas as pd

from opengsync_db import models, SyncSession, queries as Q


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

def get_barcode_table(session: AsyncSession, libraries: Sequence[models.Library]) -> pd.DataFrame:
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
                    kit_i7 = session.get_one(Q.index_kit.select(id=kit_i7_id))
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
                    kit_i5 = session.get_one(Q.index_kit.select(id=kit_i5_id))
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


def check_index_constraints(indices: list[str], must_have_bases: list[str] = ['T', 'C']) -> bool:    
    bases = set([c.upper() for c in must_have_bases])

    if len(indices) == 0:
        raise ValueError("At least one index must be provided")
    
    lens = len(indices[0])
    for index in indices:
        if len(index) != lens:
            raise ValueError("All indices must have the same length")

    for idx in range(lens):
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