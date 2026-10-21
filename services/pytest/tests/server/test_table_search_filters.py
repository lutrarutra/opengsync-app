"""HTMX table column search, filter and sort narrow / order the rendered rows.

Each test renders a table holding a row that matches and one that does not, sending the query
parameter the column header sends (``<label>=``, ``<label>_in=[ids]``, ``order_by=``), and checks
only the matching row is rendered. Name searches are trigram-fuzzy, so the two rows get names
that share no trigrams.
"""

import json

import sqlalchemy as sa
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ..db.create_units import (
    create_experiment, create_feature, create_feature_kit, create_file, create_group, create_index_kit,
    create_library, create_pool, create_project, create_protocol, create_seq_request, create_sequencer,
    create_user,
)
from ._http import get

HIT, MISS = "Zephyrine", "Bodkin"


def _html(client: TestClient, token: str, path: str, **params) -> str:
    response = get(client, path, token=token, htmx=True, params=params)
    assert response.status_code == 200, response.text[:500]
    return response.text


def _only(html: str, hit: str, miss: str) -> None:
    assert hit in html
    assert miss not in html


def _ids(*enums) -> str:
    return json.dumps([e.id for e in enums])


def _named_user(session: SyncSession, first_name: str, last_name: str = "Quill") -> models.User:
    user = create_user(session)
    user.first_name, user.last_name = first_name, last_name
    return user


# users / assignees

def test_user_table_search(client: TestClient, session: SyncSession, insider_token: str):
    hit, miss = _named_user(session, HIT, "Wonderland"), _named_user(session, MISS, "Builder")
    session.commit()

    _only(_html(client, insider_token, "/htmx/users/render-table-page", id=str(hit.id)), hit.email, miss.email)
    _only(_html(client, insider_token, "/htmx/users/render-table-page", name=f"{HIT} Wonderland"), hit.email, miss.email)


def test_assignee_table_search(client: TestClient, session: SyncSession, insider, insider_token: str):
    hit, miss = _named_user(session, HIT), _named_user(session, MISS)
    project = create_project(session, insider)
    project.assignees.extend([hit, miss])
    session.commit()

    path = "/htmx/users/render-assignee-table-page"
    _only(_html(client, insider_token, path, project_id=project.id, id=f"#{hit.id}"), hit.email, miss.email)
    _only(_html(client, insider_token, path, project_id=project.id, name=HIT), hit.email, miss.email)


# id searches

def test_pool_table_id_search(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    hit, miss = create_pool(session, insider, seq_request), create_pool(session, insider, seq_request)
    session.commit()

    _only(_html(client, insider_token, "/htmx/pools/render-table-page", id=f"P{hit.id}"), hit.name, miss.name)


def test_project_table_id_search(client: TestClient, session: SyncSession, insider, insider_token: str):
    hit, miss = create_project(session, insider), create_project(session, insider)
    session.commit()

    _only(_html(client, insider_token, "/htmx/projects/render-table-page", id=str(hit.id)), hit.title, miss.title)


def test_id_search_without_digits_is_ignored(client: TestClient, session: SyncSession, insider_token: str):
    protocol = create_protocol(session)
    session.commit()

    assert protocol.name in _html(client, insider_token, "/htmx/protocols/render-table-page", id="abc")


# seq requests

def test_seq_request_table_search_and_filters(client: TestClient, session: SyncSession, insider, insider_token: str):
    hit = create_seq_request(session, insider, submission_type=C.SubmissionType.RAW_SAMPLES)
    miss = create_seq_request(session, insider, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    library = create_library(session, insider, hit)
    library.type = C.LibraryType.TENX_SC_GEX_FLEX
    create_library(session, insider, miss)
    session.commit()

    path = "/htmx/seq_requests/render-table-page"
    _only(_html(client, insider_token, path, id=str(hit.id)), hit.name, miss.name)
    _only(_html(client, insider_token, path, library_types_in=_ids(C.LibraryType.TENX_SC_GEX_FLEX)), hit.name, miss.name)
    html = _html(client, insider_token, path, submission_type_in=_ids(C.SubmissionType.RAW_SAMPLES))
    _only(html, hit.name, miss.name)
    assert '"submission_type_in": "[1]"' in html  # selection is echoed into the table state


# experiments

def test_experiment_table_search_and_filters(client: TestClient, session: SyncSession, insider_token: str):
    hit_operator, miss_operator = _named_user(session, HIT), _named_user(session, MISS)
    hit = create_experiment(session, hit_operator, C.ExperimentWorkFlow.NOVASEQ_6K_S1_XP)
    miss = create_experiment(session, miss_operator, C.ExperimentWorkFlow.NOVASEQ_6K_S1_XP)
    hit.name, miss.name = "ExpHit", "ExpMiss"
    seq_request = create_seq_request(session, hit_operator)
    library = create_library(session, hit_operator, seq_request)
    library.type = C.LibraryType.TENX_SC_GEX_FLEX
    library.experiment_id = hit.id
    session.commit()

    path = "/htmx/experiments/render-table-page"
    _only(_html(client, insider_token, path, id=str(hit.id)), hit.name, miss.name)
    _only(_html(client, insider_token, path, operator=HIT), hit.name, miss.name)
    _only(_html(client, insider_token, path, library_types_in=_ids(C.LibraryType.TENX_SC_GEX_FLEX)), hit.name, miss.name)


# sequencers

def test_sequencer_table_search_and_filters(client: TestClient, session: SyncSession, insider_token: str):
    hit, miss = create_sequencer(session), create_sequencer(session)
    hit.name, miss.name = HIT, MISS
    hit.model = C.SequencerModel.MI_SEQ
    session.commit()

    path = "/htmx/sequencers/render-table-page"
    _only(_html(client, insider_token, path, id=str(hit.id)), HIT, MISS)
    _only(_html(client, insider_token, path, name=HIT), HIT, MISS)
    _only(_html(client, insider_token, path, model_in=_ids(C.SequencerModel.MI_SEQ)), HIT, MISS)


# features

def test_feature_table_search(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_feature_kit(session)
    hit, miss = create_feature(session, kit), create_feature(session, kit)
    hit.name, hit.identifier = HIT, "ZPH-001"
    miss.name, miss.identifier = MISS, "BDK-777"
    session.commit()

    path = "/htmx/features/render-table-page"
    _only(_html(client, insider_token, path, feature_kit_id=kit.id, id=str(hit.id)), HIT, MISS)
    _only(_html(client, insider_token, path, feature_kit_id=kit.id, name=HIT), HIT, MISS)
    _only(_html(client, insider_token, path, feature_kit_id=kit.id, identifier="ZPH-001"), HIT, MISS)


# adapters

def _adapter(session: SyncSession, kit: models.IndexKit, well: str, name: str) -> models.Adapter:
    adapter = session.save(Q.adapter.create(index_kit=kit, well=well), flush=True)
    for type in (C.BarcodeType.INDEX_I7, C.BarcodeType.INDEX_I5):
        session.save(Q.barcode.create(name=name, sequence="ACGTACGT", well=well, type=type, adapter=adapter), flush=True)
    return adapter


def test_adapter_table_search_and_name_sort(client: TestClient, session: SyncSession, insider_token: str):
    kit = create_index_kit(session)
    hit, _ = _adapter(session, kit, "A1", HIT), _adapter(session, kit, "B2", MISS)
    session.commit()

    path = "/htmx/adapters/render-table-page"
    _only(_html(client, insider_token, path, index_kit_id=kit.id, id=str(hit.id)), HIT, MISS)
    _only(_html(client, insider_token, path, index_kit_id=kit.id, well="a1"), HIT, MISS)

    html = _html(client, insider_token, path, index_kit_id=kit.id, order_by="name:asc")
    assert html.index(MISS) < html.index(HIT)
    html = _html(client, insider_token, path, index_kit_id=kit.id, order_by="name:desc")
    assert html.index(HIT) < html.index(MISS)


# media files

def test_media_file_table_search(client: TestClient, session: SyncSession, insider, insider_token: str):
    seq_request = create_seq_request(session, insider)
    hit, miss = create_file(session, seq_request=seq_request), create_file(session, seq_request=seq_request)
    hit.uploader.first_name, miss.uploader.first_name = HIT, MISS
    session.commit()

    path = "/htmx/files/render-table-page"
    _only(_html(client, insider_token, path, seq_request_id=seq_request.id, id=str(hit.id)), hit.name, miss.name)
    _only(_html(client, insider_token, path, seq_request_id=seq_request.id, uploader=HIT), hit.name, miss.name)


# affiliations

def test_affiliation_table_search_and_filter(client: TestClient, session: SyncSession, insider_token: str):
    group = create_group(session)
    hit, miss = _named_user(session, HIT), _named_user(session, MISS)
    session.save(Q.affiliation.create(user=hit, group=group, type=C.AffiliationType.MEMBER), flush=True)
    session.save(Q.affiliation.create(user=miss, group=group, type=C.AffiliationType.MANAGER), flush=True)
    hit_group, miss_group = create_group(session), create_group(session)
    hit_group.name, miss_group.name = HIT, MISS
    for g in (hit_group, miss_group):
        session.save(Q.affiliation.create(user=hit, group=g, type=C.AffiliationType.MEMBER), flush=True)
    session.commit()

    path = "/htmx/affiliations/render-table-page"
    _only(_html(client, insider_token, path, group_id=group.id, user_name=HIT), hit.email, miss.email)
    _only(_html(client, insider_token, path, group_id=group.id, affiliation_in=_ids(C.AffiliationType.MEMBER)), hit.email, miss.email)
    _only(_html(client, insider_token, path, user_id=hit.id, group_name=HIT), f">{HIT}<", f">{MISS}<")


# groups / protocols: sort and filter state

def test_group_table_sort_and_filter(client: TestClient, session: SyncSession, insider_token: str):
    first, second = create_group(session), create_group(session)
    other = create_group(session)
    other.type = C.GroupType.INSTITUTION
    session.commit()

    path = "/htmx/groups/render-table-page"
    html = _html(client, insider_token, path, order_by="id:asc")
    assert html.index(first.name) < html.index(second.name)
    html = _html(client, insider_token, path, order_by="id:desc")
    assert html.index(second.name) < html.index(first.name)

    html = _html(client, insider_token, path, type_in=_ids(C.GroupType.COLLABORATION))
    _only(html, first.name, other.name)
    assert '"type_in": "[3]"' in html


def test_protocol_table_sort_and_filter(client: TestClient, session: SyncSession, insider_token: str):
    first, second = create_protocol(session), create_protocol(session)
    session.commit()

    path = "/htmx/protocols/render-table-page"
    html = _html(client, insider_token, path, order_by="id:asc")
    assert html.index(first.name) < html.index(second.name)
    html = _html(client, insider_token, path, order_by="id:desc")
    assert html.index(second.name) < html.index(first.name)

    html = _html(client, insider_token, path, service_type_in=_ids(C.ServiceType.CUSTOM))
    assert first.name in html
    assert f'"service_type_in": "[{C.ServiceType.CUSTOM.id}]"' in html


# share tokens / data paths / api tokens

def test_share_token_table_search(client: TestClient, session: SyncSession, insider_token: str):
    hit_owner, miss_owner = _named_user(session, HIT), _named_user(session, MISS)
    hit = session.save(Q.share_token.create(owner=hit_owner, time_valid_min=60, paths=["shared"]), flush=True)
    session.save(Q.share_token.create(owner=miss_owner, time_valid_min=60, paths=["shared"]), flush=True)
    session.commit()

    path = "/htmx/share_tokens/render-table-page"
    _only(_html(client, insider_token, path, uuid=hit.uuid[:30].upper()), HIT, MISS)
    _only(_html(client, insider_token, path, owner=HIT), HIT, MISS)


def test_api_token_table_owner_search(client: TestClient, session: SyncSession, insider_token: str):
    hit_owner, miss_owner = _named_user(session, HIT), _named_user(session, MISS)
    for owner in (hit_owner, miss_owner):
        session.save(Q.api_token.create(owner=owner, time_valid_min=60), flush=True)
    session.commit()

    path = "/htmx/api-tokens/render-table-page"
    _only(_html(client, insider_token, path, owner_id=str(hit_owner.id)), HIT, MISS)
    _only(_html(client, insider_token, path, owner_id=HIT), HIT, MISS)


# sort-only model attributes (values are covered in tests/db/test_hybrid_properties.py)

def test_library_barcode_orientation_sort(session: SyncSession, insider):
    seq_request = create_seq_request(session, insider)
    forward, reverse, unindexed = (create_library(session, insider, seq_request) for _ in range(3))
    for library, orientations in (
        (forward, [C.BarcodeOrientation.REVERSE_COMPLEMENT, C.BarcodeOrientation.FORWARD]),
        (reverse, [C.BarcodeOrientation.REVERSE_COMPLEMENT]),
    ):
        for orientation in orientations:
            session.save(Q.library_index.create(
                library_id=library.id, name_i7="i7", name_i5=None, sequence_i7="ACGTAGGT", sequence_i5=None,
                index_kit_i7_id=None, index_kit_i5_id=None, orientation=orientation,
            ), flush=True)
    session.commit()

    ordered = session.scalars(
        sa.select(models.Library)
        .where(models.Library.id.in_([forward.id, reverse.id, unindexed.id]))
        .order_by(sa.nulls_last(models.Library.barcode_orientation.asc()))
    ).all()
    assert [library.id for library in ordered] == [forward.id, reverse.id, unindexed.id]
