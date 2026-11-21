"""The search box of the htmx tables also searches joined data, ranks by relevance and keeps counts right.

``owner:``, ``group:`` and ``project:`` reach through relationships as correlated EXISTS, so a library whose
two samples are in the same project is still one row (and counted once). Without an explicit sort the rows
come by relevance (exact > prefix > substring); a column sort overrides that. Unknown fields stay text,
a term that can match nothing hides everything rather than being ignored.
"""
import re

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, categories as C

from ..db.create_units import (
    create_group, create_library, create_project, create_sample, create_seq_request, create_user,
)
from ._http import get

PATH = "/htmx/libraries/render-table-page"


def _html(client: TestClient, token: str, **params) -> str:
    response = get(client, PATH, token=token, htmx=True, params=params)
    assert response.status_code == 200, response.text[:300]
    return response.text


def _total(html: str) -> int:
    match = re.search(r'class="otable-total">(\d+) librar(?:y|ies)<', html)
    assert match, "no total in the table"
    return int(match.group(1))


def _order(html: str, *names: str) -> list[str]:
    return sorted(names, key=html.index)


def test_owner_group_and_project_search(client: TestClient, session: SyncSession, insider_token: str):
    alice, bob = create_user(session), create_user(session)
    alice.first_name, alice.last_name = "Alvarez", "Quintero"
    bob.first_name, bob.last_name = "Bergmann", "Holt"
    group = create_group(session)
    group.name = "Glacier Genomics"
    req_a, req_b = create_seq_request(session, alice), create_seq_request(session, bob)
    req_a.group = group
    lib_a, lib_b = create_library(session, alice, req_a), create_library(session, bob, req_b)
    lib_a.name, lib_b.name = "FIRST_LIB", "SECOND_LIB"

    project = create_project(session, alice)
    project.title = "Osprey Migration"
    for _ in range(2):  # two samples of the same project: still one row
        sample = create_sample(session, alice, project)
        session.add(models.links.SampleLibraryLink(sample_id=sample.id, library_id=lib_a.id))
    session.commit()

    html = _html(client, insider_token, q="owner:alvarez")
    assert "FIRST_LIB" in html and "SECOND_LIB" not in html

    html = _html(client, insider_token, q='group:"glacier genomics"')
    assert "FIRST_LIB" in html and "SECOND_LIB" not in html

    html = _html(client, insider_token, q="project:osprey")
    assert "FIRST_LIB" in html and "SECOND_LIB" not in html
    assert _total(html) == 1

    # a bare term searches every field, the joined ones too
    html = _html(client, insider_token, q="bergmann")
    assert "SECOND_LIB" in html and "FIRST_LIB" not in html

    # terms are AND-ed
    assert _total(_html(client, insider_token, q="owner:alvarez second")) == 0


def test_id_search(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    for _ in range(10):  # a two-digit id: one-digit terms only match ids, not text
        create_library(session, insider, seq_request)
    hit, miss = create_library(session, insider, seq_request), create_library(session, insider, seq_request)
    session.flush()
    hit.name, miss.name = "HIT_LIB", f"MISS_LIB_{hit.id}"  # the miss carries the hit's id in its name
    session.commit()

    # a number: the row with exactly that id first, then names containing the digits
    for q in (f"#{hit.id}", str(hit.id)):
        html = _html(client, insider_token, q=q)
        assert "HIT_LIB" in html and "MISS_LIB" in html, q
        assert html.index("HIT_LIB") < html.index("MISS_LIB"), q
    # id: only the id
    html = _html(client, insider_token, q=f"id:{hit.id}")
    assert "HIT_LIB" in html and "MISS_LIB" not in html
    # an id field with text can match nothing
    assert _total(_html(client, insider_token, q="id:abc")) == 0


def test_relevance_order_and_explicit_sort(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    names = ["MY_KESTREL", "KESTREL_NEST", "KESTREL"]  # substring, prefix, exact; newest first by default
    for name in names:
        create_library(session, insider, seq_request).name = name
    session.commit()

    html = _html(client, insider_token, q="kestrel")
    assert _order(html, *names) == ["KESTREL", "KESTREL_NEST", "MY_KESTREL"]

    html = _html(client, insider_token, q="kestrel", order_by="name:asc")
    assert _order(html, *names) == sorted(names)


def test_unknown_field_is_text_and_counts_stay_right(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    create_library(session, insider, seq_request).name = "color:red"
    for i in range(3):
        create_library(session, insider, seq_request).name = f"BULK_{i}"
    session.commit()

    assert "color:red" in _html(client, insider_token, q="color:red")
    html = _html(client, insider_token, q="bulk", limit=2)
    assert _total(html) == 3
    assert "Showing 1–2 of 3" in html


def test_filtered_out_empty_state_counts_what_is_hidden(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    create_library(session, insider, seq_request).name = "ONLY_LIB"
    session.commit()

    html = _html(client, insider_token, seq_request_id=seq_request.id, q="nothing-like-this")
    assert "No libraries match" in html
    assert "1 libraries hidden by the search and filters" in html

    empty = create_seq_request(session, insider)
    session.commit()
    assert "No libraries yet" in _html(client, insider_token, seq_request_id=empty.id)


def test_status_term_in_search_box_filters(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    pooled, draft = create_library(session, insider, seq_request), create_library(session, insider, seq_request)
    pooled.name, draft.name = "POOLED_ONE", "DRAFT_ONE"
    pooled.status = C.LibraryStatus.POOLED
    session.commit()

    html = _html(client, insider_token, q="status:pooled")
    assert "POOLED_ONE" in html and "DRAFT_ONE" not in html
