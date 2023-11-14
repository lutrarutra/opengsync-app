import difflib

similars = {
    "index1(i7)": "index_1",
    "index1": "index_1",
    "i7": "index_1",
    "barcode": "index_1",
    "index2(i5)": "index_2",
    "index2": "index_2",
    "i5": "index_2",
    "index3": "index_3",
    "index4": "index_4",
    "adapter": "adapter",
    "organism": "organism",
    "samplename": "sample_name",
    "librarytype": "library_type",
}


def connect_similar_strings(refs: list[tuple[str, str]], data: list[str]) -> dict[str, str]:
    search_dict = dict([(val.lower().replace(" ", "").replace("_", ""), key) for key, val in refs])
    res = []
    for word in data:
        _word = word.lower().replace(" ", "").replace("_", "")
        if _word in similars.keys():
            res.append(similars[_word])
        else:
            closest_match = difflib.get_close_matches(word, search_dict.keys(), 1)
            if len(closest_match) == 0:
                res.append("")
            else:
                res.append(search_dict[closest_match[0]])

    return dict(zip(data, res))
