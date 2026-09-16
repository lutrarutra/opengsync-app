"""RelibWorkflow: selection, spreadsheet editing, navigation, and authorization."""

import json
import uuid

import pytest
from redis import Redis

from opengsync_db import SyncSession, categories as C, queries as Q

from ...db.create_units import create_library, create_seq_request
from .._http import (
    OpenGSyncTestClient,
    assert_form_invalid,
    assert_flash,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
    spreadsheet_payload,
)


RELIB_PREFIX = "/htmx/workflows/relib"
TABLE_COLUMNS = [
    "Library ID",
    "Sample Name",
    "Library Name",
    "Library Type",
    "Genome",
    "Assay/Service Type",
    "Nuclei",
]


def _table_payload(*rows: list[object]) -> dict[str, str]:
    return spreadsheet_payload(TABLE_COLUMNS, list(rows))


def _create_relib_libraries(session: SyncSession, user) -> tuple:
    seq_request = create_seq_request(session, user)
    library_a = create_library(session, user, seq_request)
    library_a.sample_name = "Sample_A"
    library_a.name = "Sample_A_BULKRNA"
    library_b = create_library(session, user, seq_request)
    library_b.sample_name = "Sample_B"
    library_b.name = "Sample_B_BULKRNA"
    session.commit()
    return seq_request, library_a, library_b


def _begin_and_select(
    client: OpenGSyncTestClient,
    token: str,
    seq_request_id: int,
    library_ids: list[int],
) -> dict[str, str]:
    params = {"uuid": str(uuid.uuid4()), "seq_request_id": seq_request_id}
    begun = get(client, f"{RELIB_PREFIX}/begin", token, params=params)
    assert begun.status_code == 200

    selected = post_form(
        client,
        f"{RELIB_PREFIX}/select-samples",
        {"selected_library_ids": json.dumps(library_ids)},
        token=token,
        params=params,
    )
    assert selected.status_code == 200
    assert "Edit Libraries" in selected.text
    return params


def test_relib_begin_requires_insider_and_valid_context(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    user_token: str,
    insider_token: str,
):
    seq_request = create_seq_request(session, user)
    session.commit()

    assert get(
        client,
        f"{RELIB_PREFIX}/begin",
        user_token,
        params={"seq_request_id": seq_request.id},
    ).status_code == 403
    assert get(
        client,
        f"{RELIB_PREFIX}/begin",
        insider_token,
        params={"seq_request_id": 999999},
    ).status_code == 404
    assert get(
        client,
        f"{RELIB_PREFIX}/begin",
        insider_token,
        params={"lab_prep_id": 999999},
    ).status_code == 404


def test_relib_selects_multiple_libraries_updates_values_and_cleans_state(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request, library_a, library_b = _create_relib_libraries(session, user)
    params = _begin_and_select(
        client,
        insider_token,
        seq_request.id,
        [library_a.id, library_b.id],
    )

    response = post_form(
        client,
        f"{RELIB_PREFIX}/library-edit-table",
        _table_payload(
            [
                library_a.id,
                "Sample_A_Updated",
                library_a.name,
                C.LibraryType.WGS.display_name,
                C.GenomeRef.MOUSE.display_name,
                C.ServiceType.WGS.display_name,
                "Yes",
            ],
            [
                library_b.id,
                "Sample_B_Updated",
                "Renamed_BULKRNA",
                C.LibraryType.BULK_RNA_SEQ.display_name,
                C.GenomeRef.HUMAN.display_name,
                C.ServiceType.BULK_RNA_SEQ.display_name,
                "No",
            ],
        ),
        token=insider_token,
        params=params,
    )

    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert_flash(response, "Changes Saved!", "success")

    session.expire_all()
    updated_a = session.get_one(Q.library.select(id=library_a.id))
    updated_b = session.get_one(Q.library.select(id=library_b.id))
    assert updated_a.sample_name == "Sample_A_Updated"
    assert updated_a.name == "Sample_A_WGS"
    assert updated_a.type == C.LibraryType.WGS
    assert updated_a.genome_ref == C.GenomeRef.MOUSE
    assert updated_a.service_type == C.ServiceType.WGS
    assert updated_a.nuclei_isolation is True
    assert updated_b.sample_name == "Sample_B_Updated"
    assert updated_b.name == "Renamed_BULKRNA"
    assert updated_b.type == C.LibraryType.BULK_RNA_SEQ
    assert updated_b.nuclei_isolation is False

    leftover = Redis(connection_pool=client.app.state.redis_pool).keys(
        f"RelibWorkflow:{params['uuid']}:*"
    )
    assert leftover == []


def test_relib_rejects_empty_selection_invalid_table_and_csrf(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request, library_a, _ = _create_relib_libraries(session, user)
    params = {"uuid": str(uuid.uuid4()), "seq_request_id": seq_request.id}
    assert get(client, f"{RELIB_PREFIX}/begin", insider_token, params=params).status_code == 200

    assert_form_invalid(post_form(
        client,
        f"{RELIB_PREFIX}/select-samples",
        {"selected_library_ids": "[]"},
        token=insider_token,
        params=params,
    ), "Please select at least one item.")
    assert_form_invalid(post_form_csrf_mismatch(
        client,
        f"{RELIB_PREFIX}/select-samples",
        {"selected_library_ids": json.dumps([library_a.id])},
        token=insider_token,
        params=params,
    ))

    selected = post_form(
        client,
        f"{RELIB_PREFIX}/select-samples",
        {"selected_library_ids": json.dumps([library_a.id])},
        token=insider_token,
        params=params,
    )
    assert selected.status_code == 200

    missing_column = spreadsheet_payload(
        TABLE_COLUMNS[:-1],
        [[
            library_a.id,
            library_a.sample_name,
            library_a.name,
            C.LibraryType.BULK_RNA_SEQ.display_name,
            C.GenomeRef.HUMAN.display_name,
            C.ServiceType.BULK_RNA_SEQ.display_name,
        ]],
    )
    assert_form_invalid(post_form(
        client,
        f"{RELIB_PREFIX}/library-edit-table",
        missing_column,
        token=insider_token,
        params=params,
    ), "Missing required column")

    invalid_category = _table_payload(
        [
            library_a.id,
            library_a.sample_name,
            library_a.name,
            "Not a library type",
            C.GenomeRef.HUMAN.display_name,
            C.ServiceType.BULK_RNA_SEQ.display_name,
            "No",
        ],
    )
    assert_form_invalid(post_form(
        client,
        f"{RELIB_PREFIX}/library-edit-table",
        invalid_category,
        token=insider_token,
        params=params,
    ), "Invalid category")

    assert_form_invalid(post_form_csrf_mismatch(
        client,
        f"{RELIB_PREFIX}/library-edit-table",
        _table_payload(
            [
                library_a.id,
                library_a.sample_name,
                library_a.name,
                C.LibraryType.BULK_RNA_SEQ.display_name,
                C.GenomeRef.HUMAN.display_name,
                C.ServiceType.BULK_RNA_SEQ.display_name,
                "No",
            ],
        ),
        token=insider_token,
        params=params,
    ))

    session.expire_all()
    unchanged = session.get_one(Q.library.select(id=library_a.id))
    assert unchanged.sample_name == library_a.sample_name
    assert unchanged.name == library_a.name


def test_relib_previous_navigation_preserves_selection_and_table_state(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request, library_a, _ = _create_relib_libraries(session, user)
    params = _begin_and_select(client, insider_token, seq_request.id, [library_a.id])

    previous = get(
        client,
        f"{RELIB_PREFIX}/select-samples",
        insider_token,
        params=params,
    )
    assert previous.status_code == 200
    assert str(library_a.id) in previous.text

    table = get(
        client,
        f"{RELIB_PREFIX}/library-edit-table",
        insider_token,
        params=params,
    )
    assert table.status_code == 200
    assert library_a.name in table.text


def test_relib_lab_prep_context_redirects_to_lab_prep(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    lab_prep = session.save(Q.lab_prep.create(
        name="Relib prep",
        creator=user,
        number=1,
        checklist_type=C.LabChecklistType.RNA_SEQ,
        service_type=C.ServiceType.BULK_RNA_SEQ,
    ), flush=True)
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    library.sample_name = "Prep_Sample"
    library.name = "Prep_Sample_BULKRNA"
    library.lab_prep_id = lab_prep.id
    session.commit()

    params = {"uuid": str(uuid.uuid4()), "lab_prep_id": lab_prep.id}
    assert get(client, f"{RELIB_PREFIX}/begin", insider_token, params=params).status_code == 200
    selected = post_form(
        client,
        f"{RELIB_PREFIX}/select-samples",
        {"selected_library_ids": json.dumps([library.id])},
        token=insider_token,
        params=params,
    )
    assert selected.status_code == 200

    response = post_form(
        client,
        f"{RELIB_PREFIX}/library-edit-table",
        _table_payload(
            [
                library.id,
                library.sample_name,
                library.name,
                C.LibraryType.BULK_RNA_SEQ.display_name,
                C.GenomeRef.HUMAN.display_name,
                C.ServiceType.BULK_RNA_SEQ.display_name,
                "No",
            ],
        ),
        token=insider_token,
        params=params,
    )

    assert_htmx_redirect(response, f"/lab_preps/{lab_prep.id}")


@pytest.mark.xfail(
    strict=True,
    reason="Relib selection does not enforce the seq_request_id context server-side.",
)
def test_relib_rejects_library_outside_requested_sequence_request(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    request_a = create_seq_request(session, user)
    request_b = create_seq_request(session, user)
    library_b = create_library(session, user, request_b)
    session.commit()
    params = {"uuid": str(uuid.uuid4()), "seq_request_id": request_a.id}

    assert get(client, f"{RELIB_PREFIX}/begin", insider_token, params=params).status_code == 200
    response = post_form(
        client,
        f"{RELIB_PREFIX}/select-samples",
        {"selected_library_ids": json.dumps([library_b.id])},
        token=insider_token,
        params=params,
    )

    assert response.status_code == 202


@pytest.mark.xfail(
    strict=True,
    reason="Relib table submission does not restrict rows to the selected libraries.",
)
def test_relib_rejects_unselected_library_in_table_submission(
    client: OpenGSyncTestClient,
    session: SyncSession,
    user,
    insider_token: str,
):
    seq_request, selected, unselected = _create_relib_libraries(session, user)
    params = _begin_and_select(client, insider_token, seq_request.id, [selected.id])

    response = post_form(
        client,
        f"{RELIB_PREFIX}/library-edit-table",
        _table_payload(
            [
                unselected.id,
                "Forged_Sample",
                unselected.name,
                C.LibraryType.BULK_RNA_SEQ.display_name,
                C.GenomeRef.HUMAN.display_name,
                C.ServiceType.BULK_RNA_SEQ.display_name,
                "No",
            ],
        ),
        token=insider_token,
        params=params,
    )

    assert response.status_code == 202
