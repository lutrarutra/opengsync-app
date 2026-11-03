"""SampleSubmissionLayoutWorkflow: container type, layout spreadsheet validation, persistence, checklists."""

import re
from html import unescape

import pytest
import sqlalchemy as sa

from opengsync_db import SyncSession, actions, categories as C, models

from ...db.create_units import create_library, create_pool, create_project, create_sample, create_seq_request
from .._http import (
    OpenGSyncTestClient,
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    flush_redis,
    get,
    post_form,
    spreadsheet_payload,
)


def _prefix(seq_request_id: int) -> str:
    return f"/htmx/workflows/sample-submission-layout/{seq_request_id}"


def _raw_samples_request(session: SyncSession, user, n: int = 3, submission_type=C.SubmissionType.RAW_SAMPLES):
    seq_request = create_seq_request(session, user, submission_type=submission_type)
    project = create_project(session, user)
    samples, libraries = [], []
    for i in range(n):
        sample = create_sample(session, user, project)
        sample.name = f"sample_{i + 1}"
        library = create_library(session, user, seq_request)
        library.name = f"library_{i + 1}"
        actions.link_sample_library(session, sample.id, library.id)
        samples.append(sample)
        libraries.append(library)
    session.commit()
    return seq_request, samples, libraries


def _select(client, token: str, seq_request_id: int, layout_type: C.SubmissionLayoutType, kind: str | None = None):
    begun = get(client, f"{_prefix(seq_request_id)}/begin", token)
    assert begun.status_code == 200, begun.text
    data: dict = {"layout_type": layout_type.id}
    if kind is not None:
        data["kind"] = kind
    uuid = _uuid(begun.text)
    return post_form(client, f"{_prefix(seq_request_id)}/select-layout-type", data, token=token, params={"uuid": uuid}), uuid


def _cell(item) -> str:
    """The "name [id]" value of the read-only item column."""
    return f"{item.name} [{item.id}]"


def _checked(html: str, value) -> bool:
    return re.search(rf'value="{value}" autocomplete="off"\s+checked', html) is not None


def _uuid(html: str) -> str:
    marker = '<div class="footer-id">'
    return html[html.index(marker) + len(marker):].split("</div>", 1)[0].strip()


def _submit_layout(client, token: str, seq_request_id: int, uuid: str, titles: list[str], rows: list[list]):
    return post_form(
        client, f"{_prefix(seq_request_id)}/layout-spreadsheet",
        spreadsheet_payload(titles, rows), token=token, params={"uuid": uuid},
    )


PLATE_TITLES = ["Sample", "Plate", "Well"]
TUBE_TITLES = ["Sample", "Tube Set", "Tube Label"]


def _layout(session: SyncSession, seq_request_id: int) -> list[models.SampleSubmissionLayout]:
    session.expire_all()
    return list(session.execute(
        sa.select(models.SampleSubmissionLayout)
        .where(models.SampleSubmissionLayout.seq_request_id == seq_request_id)
        .order_by(models.SampleSubmissionLayout.id)
    ).scalars())


# ── Model helpers ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("well, expected", [("A1", "A1"), ("a01", "A1"), (" h12 ", "H12"), ("B007", "B7")])  # type: ignore[attr-defined]
def test_normalize_well(well: str, expected: str):
    assert models.SampleSubmissionLayout.normalize_well(well) == expected


@pytest.mark.parametrize("well", ["I1", "A13", "A0", "1A", "", "AA1", "A1.5"])  # type: ignore[attr-defined]
def test_normalize_well_rejects_invalid(well: str):
    with pytest.raises(ValueError):
        models.SampleSubmissionLayout.normalize_well(well)


# ── Access ───────────────────────────────────────────────────────────────────

def test_begin_renders_big_buttons_for_owner(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, _, _ = _raw_samples_request(session, user)
    response = get(client, f"{_prefix(seq_request.id)}/begin", user_token)
    assert response.status_code == 200
    assert "submission-type-option" in response.text
    assert C.SubmissionLayoutType.PLATE.label in response.text
    assert C.SubmissionLayoutType.TUBES.label in response.text
    # Samples/Libraries choice is only for QC-only requests
    assert "What are you handing in?" not in response.text


def test_begin_forbidden_for_other_client(client: OpenGSyncTestClient, session: SyncSession, user, user_2_token: str):
    seq_request, _, _ = _raw_samples_request(session, user)
    assert get(client, f"{_prefix(seq_request.id)}/begin", user_2_token).status_code == 403


def test_submitted_request_locked_for_client_but_not_insider(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str, insider_token: str,
):
    seq_request, _, _ = _raw_samples_request(session, user)
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.commit()
    flush_redis(client)
    assert get(client, f"{_prefix(seq_request.id)}/begin", user_token).status_code == 403
    assert get(client, f"{_prefix(seq_request.id)}/begin", insider_token).status_code == 200


def test_spreadsheet_step_requires_started_run(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, _, _ = _raw_samples_request(session, user)
    response = _submit_layout(client, user_token, seq_request.id, "not-a-run", PLATE_TITLES, [])
    assert response.status_code == 400


def test_run_cannot_be_used_for_another_request(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user)
    other, _, _ = _raw_samples_request(session, user)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    response = _submit_layout(client, user_token, other.id, uuid, PLATE_TITLES, [[_cell(samples[0]), "", "A1"]])
    assert response.status_code == 400


# ── Plate ────────────────────────────────────────────────────────────────────

def test_plate_sheet_lists_samples(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user)
    response, _ = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    assert response.status_code == 200
    for title in PLATE_TITLES:
        assert f'"{title}"' in response.text
    for sample in samples:
        assert sample.name in response.text
    assert "96-well plates" in response.text  # help tab


@pytest.mark.parametrize("well", ["I1", "A13", "X"])  # type: ignore[attr-defined]
def test_plate_rejects_invalid_well(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str, well: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    response = _submit_layout(client, user_token, seq_request.id, uuid, PLATE_TITLES, [
        [_cell(samples[0]), "", "A1"],
        [_cell(samples[1]), "", well],
    ])
    assert_form_invalid(response, f"Invalid well '{well}'")
    assert _layout(session, seq_request.id) == []


def test_plate_empty_set_counts_as_one_plate(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    response = _submit_layout(client, user_token, seq_request.id, uuid, PLATE_TITLES, [
        [_cell(samples[0]), "", "A1"],
        [_cell(samples[1]), "", "a01"],
    ])
    assert_form_invalid(response, "the default plate")
    assert _layout(session, seq_request.id) == []


def test_plate_rejects_same_well_on_same_named_plate(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    response = _submit_layout(client, user_token, seq_request.id, uuid, PLATE_TITLES, [
        [_cell(samples[0]), "plate_1", "B2"],
        [_cell(samples[1]), "plate_1", "B2"],
    ])
    assert_form_invalid(response, "plate 'plate_1'")


def test_plate_saves_layout(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=3)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    response = _submit_layout(client, user_token, seq_request.id, uuid, PLATE_TITLES, [
        [_cell(samples[0]), "", "a01"],
        [_cell(samples[1]), "", "B1"],
        [_cell(samples[2]), "plate_2", "A1"],  # same well, other plate
    ])
    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert_flash(response, "Submission layout saved!")

    layout = _layout(session, seq_request.id)
    assert [(e.sample_id, e.set_name, e.position) for e in layout] == [
        (samples[0].id, "", "A1"),
        (samples[1].id, "", "B1"),
        (samples[2].id, "plate_2", "A1"),
    ]
    assert session.get(models.SeqRequest, seq_request.id).submission_layout_type == C.SubmissionLayoutType.PLATE  # type: ignore[union-attr]

    # The run is finished
    assert _submit_layout(client, user_token, seq_request.id, uuid, PLATE_TITLES, []).status_code == 400


def test_missing_position_is_rejected(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    response = _submit_layout(client, user_token, seq_request.id, uuid, PLATE_TITLES, [
        [_cell(samples[0]), "", "A1"],
        [_cell(samples[1]), "", ""],
    ])
    assert_form_invalid(response)
    assert _layout(session, seq_request.id) == []


def test_rerun_prefills_and_replaces_layout(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    _submit_layout(client, user_token, seq_request.id, uuid, PLATE_TITLES, [
        [_cell(samples[0]), "my_plate", "A1"],
        [_cell(samples[1]), "my_plate", "A2"],
    ])

    response, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    assert "my_plate" in response.text

    # Swapping wells works although the new positions are taken by the old layout
    response = _submit_layout(client, user_token, seq_request.id, uuid, PLATE_TITLES, [
        [_cell(samples[0]), "my_plate", "A2"],
        [_cell(samples[1]), "my_plate", "A1"],
    ])
    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert sorted((e.sample_id, e.position) for e in _layout(session, seq_request.id)) == sorted([
        (samples[0].id, "A2"), (samples[1].id, "A1"),
    ])


def test_switching_to_tubes_does_not_prefill_wells(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    _submit_layout(client, user_token, seq_request.id, uuid, PLATE_TITLES, [
        [_cell(samples[0]), "plate_x", "A1"],
        [_cell(samples[1]), "plate_x", "A2"],
    ])
    response, _ = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    assert "plate_x" not in response.text


def test_first_tubes_layout_prefills_labels_with_names(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    tubes, _ = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    plate, _ = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    for sample in samples:
        assert f"['{_cell(sample)}', '', '{sample.name}']" in tubes.text
        # Wells are not guessed
        assert f"['{_cell(sample)}', '', '']" in plate.text


def test_back_returns_to_type_selection(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, _, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    response = get(client, f"{_prefix(seq_request.id)}/select-layout-type", user_token, params={"uuid": uuid})
    assert response.status_code == 200
    assert _checked(response.text, C.SubmissionLayoutType.TUBES.id)


# ── Tubes ────────────────────────────────────────────────────────────────────

def test_tubes_reject_duplicate_label_in_set(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    response = _submit_layout(client, user_token, seq_request.id, uuid, TUBE_TITLES, [
        [_cell(samples[0]), "box", "Tube1"],
        [_cell(samples[1]), "box", "tube1"],
    ])
    assert_form_invalid(response, "tube set 'box'")


def test_tubes_same_label_in_other_set_is_saved(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    response = _submit_layout(client, user_token, seq_request.id, uuid, TUBE_TITLES, [
        [_cell(samples[0]), "", "1"],
        [_cell(samples[1]), "box_2", "1"],
    ])
    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert [(e.set_name, e.position) for e in _layout(session, seq_request.id)] == [("", "1"), ("box_2", "1")]


# ── Submission types ─────────────────────────────────────────────────────────

def test_pooled_request_places_pools(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    pools = [create_pool(session, user, seq_request) for _ in range(2)]
    session.commit()

    response, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    assert '"Pool"' in response.text
    response = _submit_layout(client, user_token, seq_request.id, uuid, ["Pool", "Tube Set", "Tube Label"], [
        [_cell(pools[0]), "", "1"],
        [_cell(pools[1]), "", "2"],
    ])
    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert [e.pool_id for e in _layout(session, seq_request.id)] == [pools[0].id, pools[1].id]


def test_qc_only_can_place_libraries(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, _, libraries = _raw_samples_request(session, user, n=2, submission_type=C.SubmissionType.QC_ONLY)

    begun = get(client, f"{_prefix(seq_request.id)}/begin", user_token)
    assert "What are you handing in?" in begun.text

    response, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE, kind="library")
    assert '"Library"' in response.text
    response = _submit_layout(client, user_token, seq_request.id, uuid, ["Library", "Plate", "Well"], [
        [_cell(libraries[0]), "", "A1"],
        [_cell(libraries[1]), "", "B1"],
    ])
    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert [e.library_id for e in _layout(session, seq_request.id)] == [libraries[0].id, libraries[1].id]

    # The next run pre-selects libraries
    begun = get(client, f"{_prefix(seq_request.id)}/begin", user_token)
    assert _checked(begun.text, "library")


def test_layout_removed_with_sample(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    _submit_layout(client, user_token, seq_request.id, uuid, TUBE_TITLES, [
        [_cell(samples[0]), "", "1"],
        [_cell(samples[1]), "", "2"],
    ])
    session.execute(sa.text("DELETE FROM sample_library_link WHERE sample_id = :id"), {"id": samples[0].id})
    session.execute(sa.text("DELETE FROM sample WHERE id = :id"), {"id": samples[0].id})
    session.commit()
    assert [e.sample_id for e in _layout(session, seq_request.id)] == [samples[1].id]


# ── Submit checklist ─────────────────────────────────────────────────────────

def _submit_checklist(client, token: str, seq_request_id: int) -> str:
    response = get(client, f"/htmx/seq_requests/{seq_request_id}/submit-checklist", token, htmx=True)
    assert response.status_code == 200
    return unescape(response.text)


def test_submit_checklist_optional_for_single_sample(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, _, _ = _raw_samples_request(session, user, n=1)
    html = _submit_checklist(client, user_token, seq_request.id)
    assert "🔘 Specify Sample Submission Layout (Optional)" in html


def test_submit_checklist_warns_without_layout(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, _, _ = _raw_samples_request(session, user, n=2)
    html = _submit_checklist(client, user_token, seq_request.id)
    assert "⚠️ Specify Sample Submission Layout</b>" in html


def test_submit_checklist_missing_prerequisites_without_samples(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    session.commit()
    html = _submit_checklist(client, user_token, seq_request.id)
    assert "❗ Specify Sample Submission Layout" in html


def test_submit_checklist_renders_plate(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.PLATE)
    _submit_layout(client, user_token, seq_request.id, uuid, PLATE_TITLES, [
        [_cell(samples[0]), "", "A1"],
        [_cell(samples[1]), "", "H12"],
    ])
    html = _submit_checklist(client, user_token, seq_request.id)
    assert "✅ Specify Sample Submission Layout" in html
    assert 'class="plate-cell filled"' in html
    assert samples[0].name in html and samples[1].name in html
    assert "Submission layout: 96-Well Plate" in html
    assert f"print_div('submission-layout-submit-{seq_request.id}')" in html


def test_submit_checklist_renders_tubes_in_rows_of_12(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=13)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    response = _submit_layout(client, user_token, seq_request.id, uuid, TUBE_TITLES, [
        [_cell(sample), "", str(i + 1)] for i, sample in enumerate(samples)
    ])
    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    html = _submit_checklist(client, user_token, seq_request.id)
    assert html.count('class="tube-row"') == 2
    # Printed tubes each name their request
    assert html.count(f'<span class="tube-request print-only">{seq_request.identifier}</span>') == 13
    assert f'id="submission-layout-submit-{seq_request.id}"' in html
    assert f">[{seq_request.identifier}] {seq_request.name} - {user.name} - Sample Submission<" in html


def test_submit_checklist_incomplete_after_new_sample(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    _submit_layout(client, user_token, seq_request.id, uuid, TUBE_TITLES, [
        [_cell(samples[0]), "", "1"],
        [_cell(samples[1]), "", "2"],
    ])
    project = create_project(session, user)
    sample = create_sample(session, user, project)
    library = create_library(session, user, seq_request)
    actions.link_sample_library(session, sample.id, library.id)
    session.commit()

    html = _submit_checklist(client, user_token, seq_request.id)
    assert "⚠️ Specify Sample Submission Layout" in html
    assert "2 of 3 samples have a position" in html
    assert 'class="tube"' in html


def _checklist_count(html: str) -> str:
    button = html[html.index('data-bs-target="#request-checklist-tab"'):]
    button = button[:button.index("</button>")]
    return button[button.index('<span class="tab-count'):]


def test_submit_tab_count_includes_layout_only_when_required(client: OpenGSyncTestClient, session: SyncSession, user, user_token: str):
    empty = create_seq_request(session, user, submission_type=C.SubmissionType.RAW_SAMPLES)
    single, _, _ = _raw_samples_request(session, user, n=1)
    multiple, _, _ = _raw_samples_request(session, user, n=2)
    flush_redis(client)
    assert _checklist_count(get(client, f"/seq_requests/{empty.id}", user_token).text).endswith("0/5</span>")
    assert _checklist_count(get(client, f"/seq_requests/{single.id}", user_token).text).endswith("/4</span>")
    assert _checklist_count(get(client, f"/seq_requests/{multiple.id}", user_token).text).endswith("/5</span>")


# ── Review checklist ─────────────────────────────────────────────────────────

def _review_checklist(client, token: str, seq_request_id: int) -> str:
    response = get(client, f"/htmx/seq_requests/{seq_request_id}/review-checklist", token, htmx=True)
    assert response.status_code == 200
    return unescape(response.text)


def _submitted(session: SyncSession, seq_request) -> None:
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    session.commit()


def test_review_step_not_relevant_for_single_sample(client: OpenGSyncTestClient, session: SyncSession, user, insider_token: str):
    seq_request, _, _ = _raw_samples_request(session, user, n=1)
    _submitted(session, seq_request)
    assert "🚫 Check Sample Submission Layout" in _review_checklist(client, insider_token, seq_request.id)


def test_review_step_missing_layout(client: OpenGSyncTestClient, session: SyncSession, user, insider_token: str):
    seq_request, _, _ = _raw_samples_request(session, user, n=2)
    _submitted(session, seq_request)
    html = _review_checklist(client, insider_token, seq_request.id)
    assert "❗ Check Sample Submission Layout" in html
    assert "Edit Layout" in html


def test_review_step_check_edit_and_uncheck(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str, insider, insider_token: str,
):
    seq_request, samples, _ = _raw_samples_request(session, user, n=2)
    _, uuid = _select(client, user_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    _submit_layout(client, user_token, seq_request.id, uuid, TUBE_TITLES, [
        [_cell(samples[0]), "", "1"],
        [_cell(samples[1]), "", "2"],
    ])
    _submitted(session, seq_request)
    flush_redis(client)

    html = _review_checklist(client, insider_token, seq_request.id)
    assert "⚠️ Check Sample Submission Layout" in html
    assert 'class="tube"' in html

    response = post_form(client, f"/htmx/seq_requests/{seq_request.id}/review-check/submission_layout_checked", {}, token=insider_token, htmx=True)
    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert "✅ Check Sample Submission Layout" in _review_checklist(client, insider_token, seq_request.id)
    logs = session.execute(
        sa.select(models.ChecklistLog).where(models.ChecklistLog.seq_request_id == seq_request.id, models.ChecklistLog.step == "submission_layout_checked")
    ).scalars().all()
    assert [log.checked for log in logs] == [True]

    # Insiders can edit the layout of a submitted request
    _, uuid = _select(client, insider_token, seq_request.id, C.SubmissionLayoutType.TUBES)
    response = _submit_layout(client, insider_token, seq_request.id, uuid, TUBE_TITLES, [
        [_cell(samples[0]), "", "3"],
        [_cell(samples[1]), "", "4"],
    ])
    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert [e.position for e in _layout(session, seq_request.id)] == ["3", "4"]

    response = post_form(client, f"/htmx/seq_requests/{seq_request.id}/review-uncheck/submission_layout_checked", {}, token=insider_token, htmx=True)
    assert_htmx_redirect(response, f"/seq_requests/{seq_request.id}")
    assert "⚠️ Check Sample Submission Layout" in _review_checklist(client, insider_token, seq_request.id)
