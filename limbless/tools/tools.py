from typing import Optional
import difflib


def connect_similar_strings(
    refs: list[tuple[str, str]], data: list[str],
    similars: Optional[dict[str, Optional[str | int]]] = None, cutoff: float = 0.5
) -> dict:
    search_dict = dict([(val.lower().replace(" ", "").replace("_", ""), key) for key, val in refs])

    res = []
    for word in data:
        _word = word.lower().replace(" ", "").replace("_", "")
        if similars is not None and _word in similars.keys():
            res.append(similars[_word])
        else:
            closest_match = difflib.get_close_matches(word, search_dict.keys(), n=1, cutoff=cutoff)
            if len(closest_match) == 0:
                res.append(None)
            else:
                res.append(search_dict[closest_match[0]])
                
    return dict(zip(data, res))
