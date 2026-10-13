"""LibraryRemuxWorkflow: edit the mux annotation of one multiplexed library.

As legacy ``library_remux_workflow``: needs WRITE on the library, and non-insiders only while
the library is a DRAFT. The library's mux type picks the form: Flex probe → barcode per
sample (once per library); oligo / ABC hashing → kit + feature or sequence + pattern + read
per sample. Oligo changes can be applied to the sample's links in all its libraries
("apply to all samples in pool", default when they already agree).
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C, actions

from ...db.create_units import create_feature, create_feature_kit, create_library, create_project, create_sample, create_seq_request
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch, spreadsheet_payload

FLEX_COLUMNS = ["Sample ID", "Library ID", "Demultiplexed Name", "Barcode ID"]
OLIGO_COLUMNS = ["Sample Name", "Multiplexing Pool", "Kit", "Feature", "Sequence", "Pattern", "Read"]
PATTERN = "5PNNNNNNNNNN(BC)"


def _url(client: TestClient, route: str) -> str:
    return client.app.url_path_for(f"LibraryRemuxWorkflow.{route}")  # type: ignore[attr-defined]


class Setup:
    """A draft request owned by ``user`` with samples Smpl1, Smpl2 in pool 'PoolA'."""

    def __init__(self, session: SyncSession, user: models.User):
        self.session = session
        self.user = user
        self.seq_request = create_seq_request(session, user)
        project = create_project(session, user)
        self.s1, self.s2 = (create_sample(session, user, project) for _ in range(2))
        self.s1.name, self.s2.name = "Smpl1", "Smpl2"
        session.save(self.s1, flush=True)
        session.save(self.s2, flush=True)
        session.commit()

    def library(self, library_type, mux_type, mux: list[dict | None]) -> models.Library:
        library = create_library(self.session, self.user, self.seq_request)
        library.type, library.mux_type, library.sample_name = library_type, mux_type, "PoolA"
        library.name = f"PoolA_{library_type.identifier}"
        self.session.save(library, flush=True)
        for sample, m in zip((self.s1, self.s2), mux):
            actions.link_sample_library(self.session, sample.id, library.id, mux=m)
        self.session.commit()
        return library

    def mux(self, library: models.Library) -> dict[str, dict | None]:
        self.session.expire_all()
        library = self.session.get_one(Q.library.select(id=library.id))
        return {link.sample.name: (dict(link.mux) if link.mux else None) for link in library.sample_links}


@pytest.fixture
def setup(session: SyncSession, user) -> Setup:
    return Setup(session, user)


@pytest.fixture
def flex(setup: Setup) -> models.Library:
    return setup.library(C.LibraryType.TENX_SC_GEX_FLEX, C.MUXType.TENX_FLEX_PROBE, [{"barcode": "BC001"}, {"barcode": "BC002"}])


def _params(library: models.Library) -> dict[str, Any]:
    return {"library_id": library.id, "uuid": str(uuid.uuid4())}


def _flex(client: TestClient, setup: Setup, library: models.Library, token: str, barcodes: list[str]):
    rows = [[setup.s1.id, library.id, "Smpl1", barcodes[0]], [setup.s2.id, library.id, "Smpl2", barcodes[1]]]
    return post_form(client, _url(client, "FlexReMuxForm.Submit"), spreadsheet_payload(FLEX_COLUMNS, rows), token=token, params=_params(library))


# ── Access ──────────────────────────────────────────────────────────────────


def test_owner_can_remux_draft_library(client: TestClient, flex: models.Library, user_token: str):
    response = get(client, _url(client, "Begin"), user_token, params=_params(flex))

    assert response.status_code == 200, response.text
    assert "BC001" in response.text and "Smpl2" in response.text


def test_other_user_is_denied(client: TestClient, setup: Setup, flex: models.Library, user_2_token: str):
    assert get(client, _url(client, "Begin"), user_2_token, params=_params(flex)).status_code == 403
    assert _flex(client, setup, flex, user_2_token, ["BC009", "BC010"]).status_code == 403
    assert setup.mux(flex) == {"Smpl1": {"barcode": "BC001"}, "Smpl2": {"barcode": "BC002"}}


def test_owner_cannot_remux_submitted_library(client: TestClient, session: SyncSession, setup: Setup, flex: models.Library, user_token: str, insider_token: str):
    flex.status = C.LibraryStatus.ACCEPTED
    session.save(flex, flush=True)
    session.commit()

    assert get(client, _url(client, "Begin"), user_token, params=_params(flex)).status_code == 403
    assert _flex(client, setup, flex, user_token, ["BC009", "BC010"]).status_code == 403
    assert get(client, _url(client, "Begin"), insider_token, params=_params(flex)).status_code == 200


def test_unknown_library_is_404(client: TestClient, insider_token: str):
    assert get(client, _url(client, "Begin"), insider_token, params={"library_id": 999999}).status_code == 404


def test_anonymous_is_redirected_to_login(client: TestClient, flex: models.Library):
    response = get(client, _url(client, "Begin"), params=_params(flex))
    assert response.status_code == 303


def test_csrf_mismatch_changes_nothing(client: TestClient, setup: Setup, flex: models.Library, user_token: str):
    rows = [[setup.s1.id, flex.id, "Smpl1", "BC009"], [setup.s2.id, flex.id, "Smpl2", "BC010"]]
    response = post_form_csrf_mismatch(client, _url(client, "FlexReMuxForm.Submit"), spreadsheet_payload(FLEX_COLUMNS, rows), token=user_token, params=_params(flex))

    assert response.status_code != 204
    assert setup.mux(flex)["Smpl1"] == {"barcode": "BC001"}


def test_unsupported_mux_type_is_400(client: TestClient, setup: Setup, insider_token: str):
    library = setup.library(C.LibraryType.TENX_SC_GEX_3PRIME, C.MUXType.TENX_ON_CHIP, [{"barcode": "OB1"}, {"barcode": "OB2"}])
    assert get(client, _url(client, "Begin"), insider_token, params=_params(library)).status_code == 400


def test_flex_mux_on_non_flex_library_is_400(client: TestClient, setup: Setup, insider_token: str):
    library = setup.library(C.LibraryType.TENX_SC_GEX_3PRIME, C.MUXType.TENX_FLEX_PROBE, [None, None])
    assert get(client, _url(client, "Begin"), insider_token, params=_params(library)).status_code == 400


# ── Flex ────────────────────────────────────────────────────────────────────


def test_flex_barcodes_are_saved(client: TestClient, setup: Setup, flex: models.Library, user_token: str):
    response = _flex(client, setup, flex, user_token, ["BC003", "BC004"])

    assert_htmx_redirect(response, f"/libraries/{flex.id}")
    assert_flash(response, "Changes saved!", category="success")
    assert setup.mux(flex) == {"Smpl1": {"barcode": "BC003"}, "Smpl2": {"barcode": "BC004"}}


def test_flex_duplicate_barcode_is_rejected(client: TestClient, setup: Setup, flex: models.Library, user_token: str):
    response = _flex(client, setup, flex, user_token, ["BC003", "BC003"])

    assert_form_invalid(response, "Duplicate 'Barcode ID' in the same 'Sample Pool' is not allowed.")
    assert setup.mux(flex)["Smpl1"] == {"barcode": "BC001"}


# ── Oligo ───────────────────────────────────────────────────────────────────


@pytest.fixture
def oligo(setup: Setup) -> tuple[models.Library, models.Library]:
    """A CMO library and the GEX library of the same samples, both with the samples' current CMO tags."""
    tags = [{"barcode": "AAAA", "pattern": PATTERN, "read": "R2"}, {"barcode": "CCCC", "pattern": PATTERN, "read": "R2"}]
    cmo = setup.library(C.LibraryType.TENX_MUX_OLIGO, C.MUXType.TENX_OLIGO, tags)
    gex = setup.library(C.LibraryType.TENX_SC_GEX_3PRIME, C.MUXType.TENX_OLIGO, tags)
    return cmo, gex


def _oligo(client: TestClient, library: models.Library, token: str, rows: list[list[str]], apply_to_pool: bool):
    payload = spreadsheet_payload(OLIGO_COLUMNS, [[f"Smpl{i + 1}", "PoolA", *row] for i, row in enumerate(rows)])
    if apply_to_pool:
        payload["apply_to_sample_pool"] = "on"
    return post_form(client, _url(client, "OligoReMuxForm.Submit"), payload, token=token, params=_params(library))


def test_oligo_begin_prefills_tags(client: TestClient, oligo, user_token: str):
    cmo, _ = oligo
    response = get(client, _url(client, "Begin"), user_token, params=_params(cmo))

    assert response.status_code == 200, response.text
    assert "AAAA" in response.text and "CCCC" in response.text


def test_oligo_changes_only_this_library(client: TestClient, setup: Setup, oligo, user_token: str):
    cmo, gex = oligo
    response = _oligo(client, cmo, user_token, [["", "", "GGGG", PATTERN, "R2"], ["", "", "TTTT", PATTERN, "R1"]], apply_to_pool=False)

    assert_htmx_redirect(response, "tab=library-multiplexing-tab")
    assert setup.mux(cmo) == {
        "Smpl1": {"barcode": "GGGG", "pattern": PATTERN, "read": "R2"},
        "Smpl2": {"barcode": "TTTT", "pattern": PATTERN, "read": "R1"},
    }
    assert setup.mux(gex)["Smpl1"]["barcode"] == "AAAA"


def test_oligo_applies_to_all_libraries_of_the_samples(client: TestClient, setup: Setup, oligo, user_token: str):
    cmo, gex = oligo
    _oligo(client, cmo, user_token, [["", "", "GGGG", PATTERN, "R2"], ["", "", "TTTT", PATTERN, "R1"]], apply_to_pool=True)

    assert setup.mux(gex) == setup.mux(cmo)
    assert setup.mux(gex)["Smpl1"]["barcode"] == "GGGG"


def test_oligo_kit_feature_fills_sequence(client: TestClient, session: SyncSession, setup: Setup, oligo, user_token: str):
    cmo, _ = oligo
    kit = create_feature_kit(session)
    kit.type = C.FeatureType.CMO
    session.save(kit, flush=True)
    for name, sequence in (("CMO301", "ATGAGGAATTCCTGC"), ("CMO302", "CATGCCAATAGAGCG")):
        feature = create_feature(session, kit)
        feature.name, feature.sequence, feature.pattern, feature.read = name, sequence, PATTERN, "R2"
        session.save(feature, flush=True)
    session.commit()
    label = f"[{kit.identifier}] {kit.name}"

    _oligo(client, cmo, user_token, [[label, "CMO301", "", "", ""], [label, "CMO302", "", "", ""]], apply_to_pool=False)

    assert setup.mux(cmo)["Smpl2"] == {"barcode": "CATGCCAATAGAGCG", "pattern": PATTERN, "read": "R2"}


@pytest.mark.parametrize("rows", [
    [["", "", "", "", ""], ["", "", "TTTT", PATTERN, "R1"]],
    [["", "", "GGGG", PATTERN, "R2"], ["", "", "GGGG", PATTERN, "R2"]],
])
def test_oligo_invalid_definitions_are_rejected(client: TestClient, setup: Setup, oligo, user_token: str, rows):
    cmo, _ = oligo
    response = _oligo(client, cmo, user_token, rows, apply_to_pool=False)

    assert_form_invalid(response)
    assert setup.mux(cmo)["Smpl1"]["barcode"] == "AAAA"
