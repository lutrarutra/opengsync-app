from typing import Optional, Union
import difflib

import pandas as pd


def make_filenameable(val, keep: list[str] = ['-', '.', '_']) -> Optional[str]:
    if pd.isna(val) or val is None:
        return None
    return "".join(c for c in str(val) if c.isalnum() or c in keep)


def make_alpha_numeric(val, keep: list[str] = []) -> Optional[str]:
    if pd.isna(val) or val is None:
        return None
    return "".join(c for c in val if c.isalnum() or c in keep)


def make_numeric(val: Union[int, float, str, None]) -> Union[int, float, None]:
    if isinstance(val, int) or isinstance(val, float):
        return val
    if isinstance(val, str):
        try:
            return int("".join(c for c in val if c.isnumeric() or c == "."))
        except ValueError:
            try:
                return float("".join(c for c in val if c.isnumeric() or c == "."))
            except ValueError:
                return None
    return None


def connect_similar_strings(
    refs: list[tuple[str, str]], data: list[str],
    similars: Optional[dict[str, str | int]] = None, cutoff: float = 0.5
) -> dict:
    search_dict = dict([(val.lower().replace(" ", "").replace("_", "").replace("-", ""), key) for key, val in refs])

    res = []
    for word in data:
        _word = word.lower().replace(" ", "").replace("_", "")
        if similars is not None and _word in similars.keys():
            res.append((similars[_word], 1.0))
        else:
            closest_match = difflib.get_close_matches(word, search_dict.keys(), n=1, cutoff=cutoff)
            if len(closest_match) == 0:
                res.append(None)
            else:
                score = difflib.SequenceMatcher(None, word, closest_match[0]).ratio()
                res.append((search_dict[closest_match[0]], score))

    data = dict(zip(data, res))
    bests = {}
    for key, val in data.items():
        if val is None:
            continue
        
        if val[0] in bests.keys():
            if val[1] > bests[val[0]][1]:
                bests[val[0]] = (key, val[1])
        else:
            bests[val[0]] = (key, val[1])

    res = {}
    for key, val in data.items():
        if val is None:
            res[key] = None
            continue

        if val[0] in bests.keys():
            if bests[val[0]][0] == key:
                res[key] = val[0]
            else:
                res[key] = None
    return res
