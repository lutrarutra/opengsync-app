"""Navbar global search: query parsing, tiered ranking in Postgres, and the insider-only route."""

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q, categories as C

from ..db.create_units import (
    create_user, create_project, create_seq_request, create_sample, create_library,
    create_kit, create_index_kit,
)
from ._http import get


def _search(session: SyncSession, text: str, kinds: list[str] | None = None, limit: int = 5):
    query = Q.search.SearchQuery.parse(text)
    assert query is not None
    session.execute(Q.search.threshold_statement())
    return session.execute(Q.search.search(query, kinds, limit_per_kind=limit)).all()


def _scores(rows, kind: str) -> dict[str, float]:
    return {row.label: row.score for row in rows if row.kind == kind}


def _libraries(session: SyncSession, *names: str):
    owner = create_user(session)
    seq_request = create_seq_request(session, owner)
    libraries = []
    for name in names:
        library = create_library(session, owner, seq_request)
        library.name = name
        libraries.append(session.save(library, flush=True))
    return libraries


# --- parsing ---

def test_parse_rejects_short_and_normalizes_whitespace():
    assert Q.search.SearchQuery.parse(None) is None
    assert Q.search.SearchQuery.parse(" a ") is None
    query = Q.search.SearchQuery.parse("  PBMC   scRNA_01 ")
    assert query is not None
    assert query.text == "pbmc scrna_01"
    assert query.compact == "pbmcscrna01"


@pytest.mark.parametrize("text, digits", [  # type: ignore[attr-defined]
    ("BSR_0012", "0012"), ("bsr12", "12"), ("BSR-0012", "0012"), ("bsr 7", "7"),
    ("bsr_", None), ("bsr_12a", None), ("bsr_" + "9" * 12, None),
])
def test_parse_seq_request_identifier(text: str, digits: str | None):
    query = Q.search.SearchQuery.parse(text)
    assert query is not None
    assert query.seq_request_digits == digits


def test_unknown_kind_raises():
    query = Q.search.SearchQuery.parse("abc")
    assert query is not None
    with pytest.raises(ValueError):
        Q.search.search(query, ["nope"])


# --- ranking ---

def test_exact_prefix_substring_fuzzy_tiers(session: SyncSession):
    _libraries(session, "PBMC_01", "PBMC_01_GEX", "X_PBMC_01_ATAC", "PBMCC_01", "unrelated")
    scores = _scores(_search(session, "pbmc_01", ["library"]), "library")

    assert scores["PBMC_01"] == 1.0
    assert scores["PBMC_01_GEX"] == 0.9
    assert scores["X_PBMC_01_ATAC"] == 0.8
    assert 0 < scores["PBMCC_01"] < 0.7  # typo: only reachable through word_similarity
    assert "unrelated" not in scores


def test_like_wildcards_in_query_match_literally(session: SyncSession):
    _libraries(session, "my_lib_1", "mylibx1", "lib%1")
    scores = _scores(_search(session, "lib_1", ["library"]), "library")
    assert scores["my_lib_1"] == 0.8
    # "_" must not act as a single-character wildcard
    assert scores.get("mylibx1", 0) < 0.7

    scores = _scores(_search(session, "b%1", ["library"]), "library")
    assert scores["lib%1"] == 0.8
    assert scores.get("my_lib_1", 0) < 0.7


def test_separator_insensitive_match(session: SyncSession):
    _libraries(session, "scRNA_seq-01.v2")
    scores = _scores(_search(session, "scrnaseq01", ["library"]), "library")
    assert scores["scRNA_seq-01.v2"] == 0.7


def test_short_query_only_matches_prefix(session: SyncSession):
    _libraries(session, "AB_lib", "lib_AB")
    scores = _scores(_search(session, "ab", ["library"]), "library")
    assert set(scores) == {"AB_lib"}


def test_total_counts_matches_beyond_limit(session: SyncSession):
    _libraries(session, *[f"limit_test_{i}" for i in range(7)])
    rows = _search(session, "limit_test", ["library"], limit=3)
    assert len(rows) == 3
    assert {row.total for row in rows} == {7}


def test_seq_request_by_identifier(session: SyncSession):
    owner = create_user(session)
    seq_request = create_seq_request(session, owner)
    rows = _search(session, f"bsr {seq_request.id}", ["seq_request"])
    assert rows[0].id == seq_request.id
    assert rows[0].score == 1.0
    assert rows[0].code == seq_request.identifier


def _named_user(session: SyncSession, first_name: str, last_name: str):
    user = create_user(session)
    user.first_name, user.last_name = first_name, last_name
    return session.save(user, flush=True)


def test_projects_and_requests_match_owner_name(session: SyncSession):
    owner = _named_user(session, "Ada", "Lovelace")
    project = create_project(session, owner)
    seq_request = create_seq_request(session, owner)

    rows = _search(session, "ada lovelace", ["project", "seq_request"])
    scores = {(row.kind, row.id): row.score for row in rows}
    assert scores[("project", project.id)] == pytest.approx(0.9)  # exact full name, person-weighted
    assert scores[("seq_request", seq_request.id)] == pytest.approx(0.9)
    assert {row.detail for row in rows} == {"Ada Lovelace"}

    # last name alone is a substring of the full name
    rows = _search(session, "lovelace", ["project"])
    assert rows[0].id == project.id and rows[0].score == pytest.approx(0.72)


def test_title_match_outranks_equal_owner_match(session: SyncSession):
    by_title = create_project(session, create_user(session))
    by_title.title = "Babbage engine"
    by_owner = create_project(session, _named_user(session, "Charles", "Babbage"))
    session.flush()

    rows = _search(session, "babbage", ["project"])
    assert [row.id for row in rows][:2] == [by_title.id, by_owner.id]


def test_library_detail_is_sample_and_request(session: SyncSession):
    (library,) = _libraries(session, "detail_check_lib")
    rows = _search(session, "detail_check_lib", ["library"])
    assert rows[0].detail == f"{library.sample_name} · {library.seq_request.identifier}"


def test_library_matches_on_sample_name_with_best_score(session: SyncSession):
    by_sample, by_both = _libraries(session, "GEX_A1", "donor-7_GEX")
    by_sample.sample_name = "Donor_7"
    by_both.sample_name = "unrelated"
    session.flush()

    rows = _search(session, "donor_7", ["library"])
    scores = {row.id: row.score for row in rows}
    assert scores[by_sample.id] == 1.0  # exact on sample_name beats the name not matching at all
    assert scores[by_both.id] == 0.7  # only the separator-insensitive name match

    by_both.sample_name = "donor_7_rep2"
    session.flush()
    scores = {row.id: row.score for row in _search(session, "donor_7", ["library"])}
    assert scores[by_both.id] == 0.9  # the better of name (0.7) and sample_name (prefix, 0.9)


def test_email_query_only_searches_users(session: SyncSession):
    user = create_user(session)
    # a library named like the address would match too if "@" did not narrow the search
    _libraries(session, user.email)
    rows = _search(session, user.email)
    assert {row.kind for row in rows} == {"user"}
    assert rows[0].id == user.id and rows[0].score == 1.0


def test_kits_are_split_by_type(session: SyncSession):
    library_kit = create_kit(session)
    library_kit.name = "kitsplit library"
    index_kit = create_index_kit(session)
    index_kit.name = "kitsplit index"
    session.flush()

    rows = _search(session, "kitsplit")
    by_kind = {row.kind: row.id for row in rows}
    assert by_kind == {"library_kit": library_kit.id, "index_kit": index_kit.id}

    rows = _search(session, "kitsplit", ["index_kit"])
    assert [row.id for row in rows] == [index_kit.id]


def test_sample_detail_is_project(session: SyncSession):
    owner = create_user(session)
    project = create_project(session, owner)
    sample = create_sample(session, owner, project)
    sample.name = "PBMC-donor_7"
    session.flush()
    rows = _search(session, "pbmc donor 7", ["sample"])
    assert rows[0].id == sample.id
    assert rows[0].detail == project.title


def test_every_kind_compiles_and_runs(session: SyncSession):
    rows = _search(session, "anything")
    assert isinstance(rows, list)


# --- route ---

def test_route_requires_insider(client: TestClient, user_token: str):
    assert get(client, "/htmx/search?q=test", token=user_token, htmx=True).status_code == 403


def test_route_rejects_unknown_kind(client: TestClient, insider_token: str):
    assert get(client, "/htmx/search?q=test&kind=nope", token=insider_token, htmx=True).status_code == 400


def test_route_short_query_returns_nothing(client: TestClient, insider_token: str):
    response = get(client, "/htmx/search?q=a", token=insider_token, htmx=True)
    assert response.status_code == 200
    assert response.text == ""


def test_route_renders_typed_grouped_results(client: TestClient, session: SyncSession, insider, insider_token: str):
    project = create_project(session, insider)
    project.title = "Navbar <b>search</b> project"
    sample = create_sample(session, insider, project)
    sample.name = "navbar_search_sample"
    session.commit()

    response = get(client, "/htmx/search?q=navbar", token=insider_token, htmx=True)
    assert response.status_code == 200
    html = response.text
    assert 'class="gs-badge">Project<' in html
    assert 'class="gs-badge">Sample<' in html
    assert f"/projects/{project.id}" in html
    assert f"/samples/{sample.id}" in html
    assert "<mark>Navbar</mark>" in html
    assert "<b>search</b>" not in html  # labels are escaped

    response = get(client, "/htmx/search?q=navbar&kind=sample", token=insider_token, htmx=True)
    assert 'class="gs-badge">Sample<' in response.text
    assert 'class="gs-badge">Project<' not in response.text
    assert "gs-section-header" not in response.text


def test_route_no_matches(client: TestClient, insider_token: str):
    response = get(client, "/htmx/search?q=zzqqxxnomatch", token=insider_token, htmx=True)
    assert "No matches" in response.text


def test_navbar_shows_search_to_insiders_only(client: TestClient, insider_token: str, user_token: str):
    assert 'id="global-search"' in get(client, "/", token=insider_token).text
    assert 'id="global-search"' not in get(client, "/", token=user_token).text
