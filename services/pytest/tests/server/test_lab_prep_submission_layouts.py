"""Lab prep checklist: optional step to print the sample submission layouts of the prep's requests."""

from opengsync_db import SyncSession, categories as C, models

from ..db.create_units import create_lab_prep, create_library, create_seq_request
from ._http import OpenGSyncTestClient, get


def _checklist(client, token: str, lab_prep_id: int) -> str:
    response = get(client, f"/htmx/lab_preps/{lab_prep_id}/checklist", token, htmx=True)
    assert response.status_code == 200, response.text
    return response.text


def test_step_needs_libraries(client: OpenGSyncTestClient, session: SyncSession, insider, insider_token: str):
    lab_prep = create_lab_prep(session, insider)
    session.commit()
    html = _checklist(client, insider_token, lab_prep.id)
    assert "❗ Print Sample Submission Layouts (Optional)" in html
    assert "No libraries in this prep." in html


def test_lists_each_request_once_with_its_sets(client: OpenGSyncTestClient, session: SyncSession, insider, insider_token: str):
    lab_prep = create_lab_prep(session, insider)
    with_layout = create_seq_request(session, insider, submission_type=C.SubmissionType.UNPOOLED_LIBRARIES)
    without_layout = create_seq_request(session, insider)
    libraries = [create_library(session, insider, with_layout) for _ in range(3)] + [create_library(session, insider, without_layout)]
    for library in libraries:
        library.lab_prep_id = lab_prep.id
    session.commit()
    session.refresh(with_layout)
    with_layout.submission_layout_type = C.SubmissionLayoutType.PLATE
    with_layout.submission_layout.extend([
        models.SampleSubmissionLayout(library_id=libraries[0].id, set_name="", position="A1"),
        models.SampleSubmissionLayout(library_id=libraries[1].id, set_name="plate_2", position="A1"),
        models.SampleSubmissionLayout(library_id=libraries[2].id, set_name="plate_2", position="B1"),
    ])
    session.commit()

    html = _checklist(client, insider_token, lab_prep.id)
    assert "🔘 Print Sample Submission Layouts (Optional)" in html
    assert "print_div('lab-prep-submission-layouts')" in html

    # One row per plate, the request spans them
    request_link = f'/seq_requests/{with_layout.id}">'
    assert html.count(request_link) == 1
    assert 'rowspan="2"' in html
    heading = f"[{with_layout.identifier}] {with_layout.name} - {insider.name} - Sample Submission"
    for i in (1, 2):
        assert f"print_div('submission-layout-labprep-{with_layout.id}-set-{i}')" in html
        # Every printable plate starts with the request heading, so prints of two requests cannot be confused
        block = html[html.index(f'id="submission-layout-labprep-{with_layout.id}-set-{i}"'):]
        assert block.index(heading) < block.index('class="plate-container')
    assert "plate_2" in html

    # A request without a layout is listed but has nothing to print
    assert f'/seq_requests/{without_layout.id}">' in html
    assert "No submission layout specified." in html
    assert f"submission-layout-labprep-{without_layout.id}" not in html
