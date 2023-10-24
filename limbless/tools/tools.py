import difflib


def connect_similar_strings(refs: list[tuple[str, str]], data: list[str]) -> dict[str, str]:
    matches = {}
    _refs = [val.lower() for _, val in refs]
    _keys = dict([(val.lower(), key) for key, val in refs])
    for query in data:
        _query = query.strip().lower()

        closest_match = difflib.get_close_matches(_query, _refs)

        if closest_match:
            matches[query] = _keys[closest_match[0]]
            _refs.remove(closest_match[0])

    return matches
