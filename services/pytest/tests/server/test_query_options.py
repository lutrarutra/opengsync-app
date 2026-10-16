"""Options for spreadsheet QueryColumns searched in several columns (core/query_options.py).

Kits match by name or identifier, projects by title or identifier, libraries by name or sample name. Rows
containing the word come first, then rows similar to it in any search column (typos), by their best similarity.
"""

import json
import random
import uuid

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, categories as C, models, queries as Q

from server.core import query_options

from ..db.create_units import create_library, create_project, create_seq_request
from ._http import get

INDEX_KITS_URL = "/htmx/index_kits/query"
KITS_URL = "/htmx/kits/query"
FEATURE_KITS_URL = "/htmx/feature_kits/query"


def _token() -> str:
    """A word that no other row contains."""
    return "q" + uuid.uuid4().hex[:10]


def _letters_token() -> str:
    """A word sharing no trigram with ``_token()``, uuids or the filler ``zzzz``: trigram matches accept a similarity of 0.05."""
    return "".join(random.choice("ghjkmntuvwxy") for _ in range(11))


def _index_kit(session: SyncSession, name: str, identifier: str, type: C.IndexType = C.IndexType.DUAL_INDEX) -> models.IndexKit:
    return session.save(Q.index_kit.create(name=name, identifier=identifier, type=type, supported_protocol_ids=[]), flush=True)


def _ids(body: dict) -> list[int]:
    return [option["id"] for option in body["options"]]


def _typo(word: str) -> str:
    """The word with two different neighbouring letters swapped, from its middle on."""
    i = next(i for i in range(len(word) // 2, len(word) - 1) if word[i] != word[i + 1])
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


# ── Index kits ──────────────────────────────────────────────────────────────


def test_index_kits_are_labelled_with_identifier_and_name(client: TestClient, session: SyncSession, user_token: str):
    kit = _index_kit(session, f"Index {_token()}", f"I{_token()}")
    session.commit()

    body = get(client, INDEX_KITS_URL, user_token, params={"word": kit.name}).json()

    assert body["options"][0] == {"id": kit.id, "name": f"[{kit.identifier}] {kit.name}"}


def test_index_kits_match_by_identifier_only(client: TestClient, session: SyncSession, user_token: str):
    kit = _index_kit(session, f"Index {_token()}", f"I{_token()}")
    session.commit()

    assert _ids(get(client, INDEX_KITS_URL, user_token, params={"word": kit.identifier}).json())[:1] == [kit.id]


def test_index_kits_match_by_name_only(client: TestClient, session: SyncSession, user_token: str):
    word = _token()
    kit = _index_kit(session, f"Index {word}", f"I{_token()}")
    session.commit()

    assert _ids(get(client, INDEX_KITS_URL, user_token, params={"word": word}).json())[:1] == [kit.id]


def test_index_kits_match_a_typo_in_the_identifier(client: TestClient, session: SyncSession, user_token: str):
    identifier = f"IDX{_token()}"
    kit = _index_kit(session, f"Index {_token()}", identifier)
    session.commit()

    assert _ids(get(client, INDEX_KITS_URL, user_token, params={"word": _typo(identifier)}).json())[:1] == [kit.id]


def test_index_kits_match_a_typo_in_the_name(client: TestClient, session: SyncSession, user_token: str):
    name = f"Index {_token()}"
    kit = _index_kit(session, name, f"I{_token()}")
    session.commit()

    assert _ids(get(client, INDEX_KITS_URL, user_token, params={"word": _typo(name)}).json())[:1] == [kit.id]


def test_index_kits_containing_the_word_come_before_similar_ones(client: TestClient, session: SyncSession, user_token: str):
    word = _token()
    # Contains the word in a long identifier (low similarity) vs. the word with a typo (high similarity)
    containing = _index_kit(session, f"Index {_token()}", f"{word}{uuid.uuid4().hex[:16]}")
    similar = _index_kit(session, f"Index {_typo(word)}", f"I{_token()}")
    session.commit()

    ids = _ids(get(client, INDEX_KITS_URL, user_token, params={"word": word}).json())

    assert containing.id in ids and similar.id in ids
    assert ids.index(containing.id) < ids.index(similar.id)


def test_index_kits_filter_by_type(client: TestClient, session: SyncSession, user_token: str):
    word = _token()
    dual = _index_kit(session, f"Index {word} dual", f"D{_token()}")
    atac = _index_kit(session, f"Index {word} atac", f"A{_token()}", type=C.IndexType.TENX_ATAC_INDEX)
    session.commit()

    params = {"word": word, "type_in": json.dumps([C.IndexType.TENX_ATAC_INDEX.id])}
    ids = _ids(get(client, INDEX_KITS_URL, user_token, params=params).json())

    assert atac.id in ids and dual.id not in ids


def test_index_kits_page_through_matches(client: TestClient, session: SyncSession, user_token: str):
    word = _token()
    kits = [_index_kit(session, f"Index {word} {i:02d}", f"I{_token()}") for i in range(25)]
    session.commit()

    first = get(client, INDEX_KITS_URL, user_token, params={"word": word, "page": 0}).json()
    second = get(client, INDEX_KITS_URL, user_token, params={"word": word, "page": 1}).json()

    assert len(first["options"]) == query_options.QUERY_PAGE_SIZE
    assert first["has_more"] is True and second["has_more"] is False
    assert {kit.id for kit in kits} == set(_ids(first) + _ids(second))


# ── Kits of every type ──────────────────────────────────────────────────────


def test_kits_of_every_type_are_offered(client: TestClient, session: SyncSession, user_token: str):
    word = _token()
    library_kit = session.save(Q.kit.create(name=f"Library {word}", identifier=f"L{_token()}", kit_type=C.KitType.LIBRARY_KIT), flush=True)
    index_kit = _index_kit(session, f"Index {word}", f"I{_token()}")
    feature_kit = session.save(Q.feature_kit.create(name=f"Feature {word}", identifier=f"F{_token()}", type=C.FeatureType.ANTIBODY), flush=True)
    session.commit()

    ids = set(_ids(get(client, KITS_URL, user_token, params={"word": word}).json()))
    assert {library_kit.id, index_kit.id, feature_kit.id} <= ids

    only_library = get(client, KITS_URL, user_token, params={"word": word, "type_in": json.dumps([C.KitType.LIBRARY_KIT.id])}).json()
    assert set(_ids(only_library)) == {library_kit.id}


def test_kits_match_a_typo_in_the_identifier(client: TestClient, session: SyncSession, user_token: str):
    identifier = f"KIT{_token()}"
    kit = session.save(Q.kit.create(name=f"Library {_token()}", identifier=identifier, kit_type=C.KitType.LIBRARY_KIT), flush=True)
    session.commit()

    assert _ids(get(client, KITS_URL, user_token, params={"word": _typo(identifier)}).json())[:1] == [kit.id]


# ── Feature kits: identifier similarity ─────────────────────────────────────


def test_feature_kits_match_a_typo_in_the_identifier(client: TestClient, session: SyncSession, user_token: str):
    identifier = f"FK{_token()}"
    kit = session.save(Q.feature_kit.create(name=f"Feature {_token()}", identifier=identifier, type=C.FeatureType.ANTIBODY), flush=True)
    session.commit()

    assert _ids(get(client, FEATURE_KITS_URL, user_token, params={"word": _typo(identifier)}).json())[:1] == [kit.id]


# ── Search columns of projects and libraries ────────────────────────────────


def _search(session: SyncSession, stmt, columns, word: str, order_column) -> list[int]:
    return [obj.id for obj in session.get_all(query_options.search(stmt, columns, word, order_column), limit=None)]


def test_projects_match_by_title_or_identifier(session: SyncSession, user):
    by_title = create_project(session, user)
    by_title.title = f"Project {_token()}"
    by_identifier = create_project(session, user)
    by_identifier.title = "zzzz"
    by_identifier.identifier = _letters_token()
    session.save(by_title, flush=True)
    session.save(by_identifier, flush=True)

    stmt = Q.project.select().where(models.Project.id.in_([by_title.id, by_identifier.id]))
    columns, order = query_options.PROJECT_SEARCH_COLUMNS, models.Project.title

    assert _search(session, stmt, columns, by_title.title.split()[1], order) == [by_title.id]
    assert _search(session, stmt, columns, by_identifier.identifier, order) == [by_identifier.id]
    assert _search(session, stmt, columns, _typo(by_identifier.identifier), order)[:1] == [by_identifier.id]


def test_libraries_match_by_name_or_sample_name(session: SyncSession, user):
    seq_request = create_seq_request(session, user)
    by_name = create_library(session, user, seq_request)
    by_name.name = f"Lib_{_token()}"
    by_name.sample_name = "zzzz"
    by_sample = create_library(session, user, seq_request)
    by_sample.name = "zzzz"
    by_sample.sample_name = f"Sample_{_letters_token()}"
    session.save(by_name, flush=True)
    session.save(by_sample, flush=True)

    stmt = Q.library.select().where(models.Library.id.in_([by_name.id, by_sample.id]))
    columns, order = query_options.LIBRARY_SEARCH_COLUMNS, models.Library.name

    assert _search(session, stmt, columns, by_name.name, order) == [by_name.id]
    assert _search(session, stmt, columns, by_sample.sample_name, order) == [by_sample.id]
    assert _search(session, stmt, columns, _typo(by_sample.sample_name), order)[:1] == [by_sample.id]
