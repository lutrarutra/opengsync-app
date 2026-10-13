"""BAReportWorkflow: record BioAnalyzer average fragment sizes with the report PDF.

As legacy ``ba_report_workflow``: insider-only. Step 1 selects samples, libraries, pools
and/or lanes (at least one, unique names). Step 2 either takes the sizes manually plus the
PDF (``method=manual``), or parses the BioAnalyzer CSV export (``method=excel``): the
parsed wells are matched to the selection in an ordering step, then confirmed with the PDF.

On save the PDF becomes a ``BIOANALYZER_REPORT`` media file (attached to the lab prep in
lab-prep context); each object gets its size and is linked to the report (an empty size
clears both); an ACCEPTED pool with a size becomes STORED.
"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import config

from ...db.create_units import (
    create_experiment, create_lab_prep, create_library, create_pool, create_project, create_sample, create_seq_request,
)
from .._http import CSRF, assert_flash, cookie_header, assert_form_invalid, assert_htmx_redirect, get, post_form

PDF = b"%PDF-1.4 fake report"


def _url(client: TestClient, route: str) -> str:
    return client.app.url_path_for(f"BAReportWorkflow.{route}")  # type: ignore[attr-defined]


def _csv(sizes: dict[str, int | str]) -> bytes:
    """BioAnalyzer CSV export: a 'Sample Name' block with a 'Region Table' per well."""
    blocks = []
    for well, size in sizes.items():
        blocks.append(
            f"Sample Name,{well}\nSample Comment,\n\nRegion Table\n"
            f"From [bp],To [bp],Average Size [bp],% of Total\n100,1000,{size},100\n"
        )
    return "\n".join(blocks).encode("latin-1")


@pytest.fixture
def media_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config.settings.app_config, "media_folder", str(tmp_path))
    return tmp_path


class Objects:
    def __init__(self, session: SyncSession, user: models.User, insider: models.User):
        self.session = session
        seq_request = create_seq_request(session, user)
        self.sample = create_sample(session, user, create_project(session, user))
        self.sample.status = C.SampleStatus.STORED
        self.library = create_library(session, user, seq_request)
        self.library.status = C.LibraryStatus.PREPARING
        self.pool = create_pool(session, user, seq_request)
        self.pool.status = C.PoolStatus.ACCEPTED
        self.experiment = create_experiment(session, insider, C.ExperimentWorkFlow.NOVASEQ_6K_SP_XP)
        for obj in (self.sample, self.library, self.pool):
            session.save(obj, flush=True)
        session.commit()
        session.refresh(self.experiment)
        self.lane = next(lane for lane in self.experiment.lanes if lane.number == 1)
        self.params: dict = {"uuid": str(uuid.uuid4())}

    def selection(self, samples=(), libraries=(), pools=(), lanes=()) -> dict[str, str]:
        return {
            "selected_sample_ids": json.dumps([o.id for o in samples]),
            "selected_library_ids": json.dumps([o.id for o in libraries]),
            "selected_pool_ids": json.dumps([o.id for o in pools]),
            "selected_lane_ids": json.dumps([o.id for o in lanes]),
        }


@pytest.fixture
def objs(session: SyncSession, user, insider, media_folder: Path) -> Objects:
    return Objects(session, user, insider)


def _select(client: TestClient, objs: Objects, token: str, **selection):
    return post_form(client, _url(client, "SelectSamplesForm.Submit"), objs.selection(**selection), token=token, params=objs.params)


def _entries(values: dict[str, list[tuple[object, str, str]]]) -> dict[str, str]:
    """``values``: list name → [(object, type, size)]."""
    data: dict[str, str] = {}
    for list_name, entries in values.items():
        for i, (obj, obj_type, size) in enumerate(entries):
            data[f"{list_name}-{i}-id_"] = str(obj.id)
            data[f"{list_name}-{i}-name"] = str(getattr(obj, "name", "lane"))
            data[f"{list_name}-{i}-type"] = obj_type
            data[f"{list_name}-{i}-avg_fragment_size"] = size
    return data


def _post_files(client: TestClient, url: str, data: dict[str, str], files: dict, token: str, params: dict):
    client.cookies.set("csrf_token", CSRF)
    return client.post(
        url, data={**data, "csrf_token": CSRF}, files=files or None,
        headers=cookie_header(client, token), params=params, follow_redirects=False,
    )


def _manual(client: TestClient, objs: Objects, token: str, values: dict, pdf: bytes | None = PDF, filename: str = "report.pdf"):
    files = {"pdf": (filename, pdf, "application/pdf")} if pdf is not None else {}
    return _post_files(client, _url(client, "BAReportForm.Submit"), _entries(values), files, token, {**objs.params, "method": "manual"})


def _excel(client: TestClient, objs: Objects, token: str, content: bytes | None, values: dict | None = None):
    files = {"ba_excel": ("export.csv", content, "text/csv")} if content is not None else {}
    return _post_files(client, _url(client, "BAReportForm.Submit"), _entries(values or {}), files, token, {**objs.params, "method": "excel"})


def _reload(session: SyncSession, model, obj_id: int):
    session.expire_all()
    return session.get(model, obj_id)


def _reports(session: SyncSession) -> list[models.MediaFile]:
    session.expire_all()
    return session.get_all(Q.media_file.select(type=C.MediaFileType.BIOANALYZER_REPORT), limit=None)


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_is_denied(client: TestClient, session: SyncSession, objs: Objects, user_token: str):
    assert get(client, _url(client, "Begin"), user_token, params=objs.params).status_code == 403
    assert _select(client, objs, user_token, samples=[objs.sample]).status_code == 403
    assert _manual(client, objs, user_token, {"sample_forms": [(objs.sample, "sample", "300")]}).status_code == 403
    assert _reload(session, models.Sample, objs.sample.id).avg_fragment_size is None


def test_anonymous_is_redirected_to_login(client: TestClient, objs: Objects):
    response = get(client, _url(client, "Begin"), params=objs.params)
    assert response.status_code == 303
    assert "/auth/login" in response.headers.get("location", "")


def test_begin_renders(client: TestClient, objs: Objects, insider_token: str):
    assert get(client, _url(client, "Begin"), insider_token, params=objs.params).status_code == 200


# ── Selection ───────────────────────────────────────────────────────────────


def test_select_one_sample(client: TestClient, objs: Objects, insider_token: str):
    response = _select(client, objs, insider_token, samples=[objs.sample])

    assert response.status_code == 200, response.text
    assert objs.sample.name in response.text


def test_select_all_object_types(client: TestClient, objs: Objects, insider_token: str):
    response = _select(client, objs, insider_token, samples=[objs.sample], libraries=[objs.library], pools=[objs.pool], lanes=[objs.lane])

    assert response.status_code == 200, response.text
    for label, name in (("sample", objs.sample.name), ("library", objs.library.name), ("pool", objs.pool.name), ("lane", f"{objs.experiment.name} - Lane 1")):
        assert name in response.text, label


def test_empty_selection_is_rejected(client: TestClient, objs: Objects, insider_token: str):
    """Legacy: 'Select at least one sample'."""
    assert_form_invalid(_select(client, objs, insider_token), "Select at least one sample")


def test_duplicate_names_are_rejected(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    objs.library.name = objs.sample.name
    session.save(objs.library, flush=True)
    session.commit()

    response = _select(client, objs, insider_token, samples=[objs.sample], libraries=[objs.library])

    assert_form_invalid(response, "Duplicate sample names selected.")


# ── Manual entry ────────────────────────────────────────────────────────────


def test_manual_sizes_are_saved_and_linked_to_report(
    client: TestClient, session: SyncSession, objs: Objects, insider, insider_token: str, media_folder: Path,
):
    _select(client, objs, insider_token, samples=[objs.sample], libraries=[objs.library], pools=[objs.pool], lanes=[objs.lane])

    response = _manual(client, objs, insider_token, {
        "sample_forms": [(objs.sample, "sample", "300")],
        "library_forms": [(objs.library, "library", "400")],
        "pool_forms": [(objs.pool, "pool", "500")],
        "lane_forms": [(objs.lane, "lane", "600")],
    })

    assert_htmx_redirect(response, "/")
    assert_flash(response, "Changes Saved!", category="success")
    [report] = _reports(session)
    assert (report.uploader_id, report.extension) == (insider.id, ".pdf")
    assert (media_folder / report.path).read_bytes() == PDF

    sample = _reload(session, models.Sample, objs.sample.id)
    library = _reload(session, models.Library, objs.library.id)
    pool = _reload(session, models.Pool, objs.pool.id)
    lane = _reload(session, models.Lane, objs.lane.id)
    assert [(o.avg_fragment_size, o.ba_report_id) for o in (sample, library, pool, lane)] == [
        (300, report.id), (400, report.id), (500, report.id), (600, report.id),
    ]
    assert pool.status == C.PoolStatus.STORED


def test_manual_empty_size_clears_size_and_report(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    objs.sample.avg_fragment_size = 250
    session.save(objs.sample, flush=True)
    session.commit()
    _select(client, objs, insider_token, samples=[objs.sample], libraries=[objs.library])

    _manual(client, objs, insider_token, {
        "sample_forms": [(objs.sample, "sample", "")],
        "library_forms": [(objs.library, "library", "400")],
    })

    sample = _reload(session, models.Sample, objs.sample.id)
    assert (sample.avg_fragment_size, sample.ba_report_id) == (None, None)


def test_manual_in_lab_prep_context_attaches_report(
    client: TestClient, session: SyncSession, objs: Objects, insider, insider_token: str,
):
    lab_prep = create_lab_prep(session, insider)
    objs.library.lab_prep_id = lab_prep.id
    session.save(objs.library, flush=True)
    session.commit()
    objs.params["lab_prep_id"] = lab_prep.id
    _select(client, objs, insider_token, libraries=[objs.library])

    response = _manual(client, objs, insider_token, {"library_forms": [(objs.library, "library", "400")]})

    assert_htmx_redirect(response, f"/lab_preps/{lab_prep.id}")
    assert [r.lab_prep_id for r in _reports(session)] == [lab_prep.id]


def test_manual_requires_pdf(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    _select(client, objs, insider_token, samples=[objs.sample])

    response = _manual(client, objs, insider_token, {"sample_forms": [(objs.sample, "sample", "300")]}, pdf=None)

    assert_form_invalid(response, "Please upload a PDF file.")
    assert _reload(session, models.Sample, objs.sample.id).avg_fragment_size is None


def test_manual_rejects_non_pdf(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    _select(client, objs, insider_token, samples=[objs.sample])

    response = _manual(client, objs, insider_token, {"sample_forms": [(objs.sample, "sample", "300")]}, filename="report.txt")

    assert_form_invalid(response)
    assert _reports(session) == []


@pytest.mark.parametrize("size", ["0", "-5", "abc"])
def test_manual_invalid_size_is_rejected(client: TestClient, session: SyncSession, objs: Objects, insider_token: str, size: str):
    _select(client, objs, insider_token, samples=[objs.sample])

    response = _manual(client, objs, insider_token, {"sample_forms": [(objs.sample, "sample", size)]})

    assert_form_invalid(response)
    assert _reports(session) == []


def test_manual_completion_clears_state(client: TestClient, objs: Objects, insider_token: str):
    _select(client, objs, insider_token, samples=[objs.sample])
    _manual(client, objs, insider_token, {"sample_forms": [(objs.sample, "sample", "300")]})

    r = Redis(connection_pool=client.app.state.redis_pool)  # type: ignore[attr-defined]
    assert list(r.scan_iter(f"BAReportWorkflow:{objs.params['uuid']}:*")) == []


def test_manual_only_updates_selected_objects(client: TestClient, session: SyncSession, objs: Objects, user, insider_token: str):
    other = create_sample(session, user, create_project(session, user))
    session.commit()
    _select(client, objs, insider_token, samples=[objs.sample])

    response = _manual(client, objs, insider_token, {"sample_forms": [(objs.sample, "sample", "300"), (other, "sample", "999")]})

    assert response.status_code == 400
    assert _reload(session, models.Sample, other.id).avg_fragment_size is None


def test_report_step_without_selection_is_400(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    response = _manual(client, objs, insider_token, {"sample_forms": [(objs.sample, "sample", "300")]})

    assert response.status_code == 400
    assert _reload(session, models.Sample, objs.sample.id).avg_fragment_size is None


# ── Excel (CSV export) ──────────────────────────────────────────────────────


def _excel_to_complete(client: TestClient, objs: Objects, token: str):
    """Select sample + library, parse two wells and map well 1 → sample, well 2 → library."""
    _select(client, objs, token, samples=[objs.sample], libraries=[objs.library])
    response = _excel(client, objs, token, _csv({"Well1": 350, "Well2": 420}))
    assert response.status_code == 200, response.text
    assert "Well1" in response.text and "Well2" in response.text

    response = post_form(client, _url(client, "ParseBAExcelFileForm.Submit"), {
        "left_order": json.dumps([0, 1]),
        "right_order": json.dumps([{"name": "Well1", "value": "350"}, {"name": "Well2", "value": "420"}]),
    }, token=token, params=objs.params)
    assert response.status_code == 200, response.text
    return response


def test_excel_parsed_sizes_are_confirmed_and_saved(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    response = _excel_to_complete(client, objs, insider_token)
    assert "350" in response.text and "420" in response.text

    response = _post_files(
        client, _url(client, "CompleteBAReport.Submit"),
        _entries({"sample_forms": [(objs.sample, "sample", "350")], "library_forms": [(objs.library, "library", "420")]}),
        {"pdf": ("report.pdf", PDF, "application/pdf")}, insider_token, objs.params,
    )

    assert_htmx_redirect(response, "/")
    [report] = _reports(session)
    assert (_reload(session, models.Sample, objs.sample.id).avg_fragment_size, _reload(session, models.Sample, objs.sample.id).ba_report_id) == (350, report.id)
    assert _reload(session, models.Library, objs.library.id).avg_fragment_size == 420


def test_excel_completion_clears_state(client: TestClient, objs: Objects, insider_token: str):
    _excel_to_complete(client, objs, insider_token)
    _post_files(
        client, _url(client, "CompleteBAReport.Submit"),
        _entries({"sample_forms": [(objs.sample, "sample", "350")], "library_forms": [(objs.library, "library", "420")]}),
        {"pdf": ("report.pdf", PDF, "application/pdf")}, insider_token, objs.params,
    )

    r = Redis(connection_pool=client.app.state.redis_pool)  # type: ignore[attr-defined]
    assert list(r.scan_iter(f"BAReportWorkflow:{objs.params['uuid']}:*")) == []


def test_excel_complete_requires_pdf(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    _excel_to_complete(client, objs, insider_token)

    response = _post_files(
        client, _url(client, "CompleteBAReport.Submit"),
        _entries({"sample_forms": [(objs.sample, "sample", "350")], "library_forms": [(objs.library, "library", "420")]}),
        {}, insider_token, objs.params,
    )

    assert_form_invalid(response)
    assert _reload(session, models.Sample, objs.sample.id).avg_fragment_size is None


def test_excel_requires_file(client: TestClient, objs: Objects, insider_token: str):
    _select(client, objs, insider_token, samples=[objs.sample])
    assert_form_invalid(_excel(client, objs, insider_token, None), "Please upload an Excel file.")


def test_excel_without_parsable_data_is_rejected(client: TestClient, objs: Objects, insider_token: str):
    """Legacy re-rendered the form with 'No valid data was parsed in the Excel file.'"""
    _select(client, objs, insider_token, samples=[objs.sample])

    response = _excel(client, objs, insider_token, b"just,some\ncsv,data\n")

    assert_form_invalid(response, "No valid data was parsed in the Excel file.")


def test_excel_zero_size_becomes_empty(client: TestClient, session: SyncSession, objs: Objects, insider_token: str):
    """Sizes must be positive (molarity divides by them): a 0 from the export or the assignment is 'unknown'."""
    _select(client, objs, insider_token, samples=[objs.sample])
    _excel(client, objs, insider_token, _csv({"Well1": 0}))

    response = post_form(client, _url(client, "ParseBAExcelFileForm.Submit"), {
        "left_order": json.dumps([0]),
        "right_order": json.dumps([{"name": "Well1", "value": "0"}]),
    }, token=insider_token, params=objs.params)

    assert response.status_code == 200, response.text
    assert 'value="0"' not in response.text


def test_excel_well_without_size_is_kept_empty(client: TestClient, objs: Objects, insider_token: str):
    _select(client, objs, insider_token, samples=[objs.sample])

    response = _excel(client, objs, insider_token, _csv({"Well1": "n/a"}))

    assert response.status_code == 200, response.text
    assert "Well1" in response.text


@pytest.mark.parametrize("left, right", [
    ("not json", "[]"),
    (json.dumps([5]), json.dumps([{"name": "Well1", "value": "350"}])),
    (json.dumps([0]), json.dumps([{"name": "Well1", "value": "abc"}])),
])
def test_malformed_order_is_rejected(client: TestClient, objs: Objects, insider_token: str, left: str, right: str):
    _select(client, objs, insider_token, samples=[objs.sample])
    _excel(client, objs, insider_token, _csv({"Well1": 350}))

    response = post_form(client, _url(client, "ParseBAExcelFileForm.Submit"), {"left_order": left, "right_order": right}, token=insider_token, params=objs.params)

    assert response.status_code in (202, 400)
