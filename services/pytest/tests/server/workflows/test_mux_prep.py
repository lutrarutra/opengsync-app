"""MuxPrepWorkflow: annotate the mux barcodes of a lab prep's multiplexed samples.

As legacy ``mux_prep_workflow``: insider-only; ``mux_type_id`` picks the flow and only the
prep's libraries of that mux type are listed. The barcodes are stored in the
sample–library link's ``mux``.

- Flex (``TENX_FLEX_PROBE``): one row per GEX Flex sample; a barcode may appear once per
  pool. If the prep has ABC Flex libraries, a second step annotates them: prefilled from
  the GEX barcode with ``BC`` → ``AB`` and limited to ``AB001``–``AB016``.
- On-chip (``TENX_ON_CHIP``): one row per sample and pool; ``1``/``OB1``/``1;2`` are
  normalized to ``OB1``/``OB1;OB2``; only ``OB1``–``OB4``, once per pool.
- Oligo (``TENX_OLIGO``): per sample either kit + feature (sequence/pattern/read from the
  kit) or sequence + pattern + read; definitions unique per pool.

Pool membership is read-only here (legacy OCM could re-pool; FastAPI moved that to
``SamplePoolingAction``).
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C, actions

from ...db.create_units import (
    create_feature, create_feature_kit, create_lab_prep, create_library, create_project, create_sample, create_seq_request,
)
from .._http import assert_flash, assert_form_invalid, assert_htmx_redirect, get, post_form, post_form_csrf_mismatch, spreadsheet_payload

GEX = C.LibraryType.TENX_SC_GEX_FLEX
ABC = C.LibraryType.TENX_SC_ABC_FLEX

FLEX_COLUMNS = ["Sample ID", "Library ID", "Sample Pool", "Demultiplexed Name", "Barcode ID"]
OCM_COLUMNS = ["Demultiplexed Name", "Sample Pool", "Barcode ID"]
OLIGO_COLUMNS = ["Sample Name", "Multiplexing Pool", "Kit", "Feature", "Sequence", "Pattern", "Read"]
PATTERN = "5PNNNNNNNNNN(BC)"


def _url(client: TestClient, route: str) -> str:
    return client.app.url_path_for(f"MuxPrepWorkflow.{route}")  # type: ignore[attr-defined]


class Prep:
    def __init__(self, session: SyncSession, user: models.User, insider: models.User):
        self.session = session
        self.user = user
        self.lab_prep = create_lab_prep(session, insider)
        self.seq_request = create_seq_request(session, user)
        project = create_project(session, user)
        self.samples = [create_sample(session, user, project) for _ in range(4)]
        for i, sample in enumerate(self.samples, start=1):
            sample.name = f"Smpl{i}"
            session.save(sample, flush=True)
        self.s1, self.s2, self.s3, self.s4 = self.samples
        self.uuid = str(uuid.uuid4())
        session.commit()

    def library(self, pool: str, library_type, samples: list[models.Sample], mux_type, mux: dict | None = None) -> models.Library:
        library = create_library(self.session, self.user, self.seq_request)
        library.name = f"{pool}_{library_type.identifier}"
        library.sample_name = pool
        library.type = library_type
        library.mux_type = mux_type
        library.lab_prep_id = self.lab_prep.id
        self.session.save(library, flush=True)
        for sample in samples:
            actions.link_sample_library(self.session, sample.id, library.id, mux=dict(mux) if mux else None)
        self.session.commit()
        return library

    def params(self, mux_type) -> dict[str, Any]:
        return {"lab_prep_id": self.lab_prep.id, "mux_type_id": mux_type.id, "uuid": self.uuid}

    def mux(self, library: models.Library) -> dict[str, dict | None]:
        """Sample name → link.mux of the library."""
        self.session.expire_all()
        library = self.session.get_one(Q.library.select(id=library.id))
        return {link.sample.name: (dict(link.mux) if link.mux else None) for link in library.sample_links}


@pytest.fixture
def prep(session: SyncSession, user, insider) -> Prep:
    return Prep(session, user, insider)


# ── Begin and access ────────────────────────────────────────────────────────


@pytest.fixture
def flex(prep: Prep) -> tuple[models.Library, models.Library]:
    """Flex GEX pools PoolA (Smpl1, Smpl2) and PoolB (Smpl3, Smpl4) with barcodes BC001/BC002 in each pool."""
    pool_a = prep.library("PoolA", GEX, [prep.s1, prep.s2], C.MUXType.TENX_FLEX_PROBE)
    pool_b = prep.library("PoolB", GEX, [prep.s3, prep.s4], C.MUXType.TENX_FLEX_PROBE)
    return pool_a, pool_b


def _flex_rows(pool_a: models.Library, pool_b: models.Library, prep: Prep, barcodes: list[str]) -> dict[str, str]:
    rows = [
        [prep.s1.id, pool_a.id, "PoolA", "Smpl1", barcodes[0]],
        [prep.s2.id, pool_a.id, "PoolA", "Smpl2", barcodes[1]],
        [prep.s3.id, pool_b.id, "PoolB", "Smpl3", barcodes[2]],
        [prep.s4.id, pool_b.id, "PoolB", "Smpl4", barcodes[3]],
    ]
    return spreadsheet_payload(FLEX_COLUMNS, rows)


def test_client_is_denied(client: TestClient, prep: Prep, flex, user_token: str):
    params = prep.params(C.MUXType.TENX_FLEX_PROBE)
    assert get(client, _url(client, "Begin"), user_token, params=params).status_code == 403
    pool_a, pool_b = flex
    response = post_form(client, _url(client, "FlexMuxForm.Submit"), _flex_rows(pool_a, pool_b, prep, ["BC001", "BC002", "BC001", "BC002"]), token=user_token, params=params)
    assert response.status_code == 403
    assert prep.mux(pool_a) == {"Smpl1": None, "Smpl2": None}


def test_anonymous_is_redirected_to_login(client: TestClient, prep: Prep):
    response = get(client, _url(client, "Begin"), params=prep.params(C.MUXType.TENX_FLEX_PROBE))
    assert response.status_code == 303
    assert "/auth/login" in response.headers.get("location", "")


def test_unknown_lab_prep_is_404(client: TestClient, insider_token: str):
    params = {"lab_prep_id": 999999, "mux_type_id": C.MUXType.TENX_FLEX_PROBE.id}
    assert get(client, _url(client, "Begin"), insider_token, params=params).status_code == 404


@pytest.mark.parametrize("mux_type_id", [999, C.MUXType.TENX_ABC_HASH.id])
def test_invalid_or_unsupported_mux_type_is_400(client: TestClient, prep: Prep, insider_token: str, mux_type_id: int):
    params = {"lab_prep_id": prep.lab_prep.id, "mux_type_id": mux_type_id}
    assert get(client, _url(client, "Begin"), insider_token, params=params).status_code == 400


def test_csrf_mismatch_changes_nothing(client: TestClient, prep: Prep, flex, insider_token: str):
    pool_a, pool_b = flex
    response = post_form_csrf_mismatch(
        client, _url(client, "FlexMuxForm.Submit"), _flex_rows(pool_a, pool_b, prep, ["BC001", "BC002", "BC001", "BC002"]),
        token=insider_token, params=prep.params(C.MUXType.TENX_FLEX_PROBE),
    )
    assert response.status_code not in (200, 204)
    assert prep.mux(pool_a) == {"Smpl1": None, "Smpl2": None}


# ── Flex ────────────────────────────────────────────────────────────────────


def test_flex_begin_lists_only_flex_samples(client: TestClient, session: SyncSession, prep: Prep, flex, insider_token: str):
    other = create_sample(session, prep.user, create_project(session, prep.user))
    other.name = "OCM_ONLY"
    session.save(other, flush=True)
    prep.library("PoolC", C.LibraryType.TENX_SC_GEX_3PRIME, [other], C.MUXType.TENX_ON_CHIP)

    response = get(client, _url(client, "Begin"), insider_token, params=prep.params(C.MUXType.TENX_FLEX_PROBE))

    assert response.status_code == 200, response.text
    for text in ("Smpl1", "Smpl4", "PoolA", "PoolB"):
        assert text in response.text
    assert "OCM_ONLY" not in response.text


def test_flex_saves_barcodes(client: TestClient, prep: Prep, flex, insider_token: str):
    pool_a, pool_b = flex
    response = post_form(
        client, _url(client, "FlexMuxForm.Submit"), _flex_rows(pool_a, pool_b, prep, ["BC001", "BC002", "BC001", "BC002"]),
        token=insider_token, params=prep.params(C.MUXType.TENX_FLEX_PROBE),
    )

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert_flash(response, "Changes saved!", category="success")
    assert prep.mux(pool_a) == {"Smpl1": {"barcode": "BC001"}, "Smpl2": {"barcode": "BC002"}}
    assert prep.mux(pool_b) == {"Smpl3": {"barcode": "BC001"}, "Smpl4": {"barcode": "BC002"}}


def test_flex_redirect_opens_mux_tab(client: TestClient, prep: Prep, flex, insider_token: str):
    """Legacy redirected to the lab prep's mux tab after Flex annotation."""
    pool_a, pool_b = flex
    response = post_form(
        client, _url(client, "FlexMuxForm.Submit"), _flex_rows(pool_a, pool_b, prep, ["BC001", "BC002", "BC001", "BC002"]),
        token=insider_token, params=prep.params(C.MUXType.TENX_FLEX_PROBE),
    )
    assert_htmx_redirect(response, "tab=mux-tab")


def test_flex_duplicate_barcode_in_pool_is_rejected(client: TestClient, prep: Prep, flex, insider_token: str):
    pool_a, pool_b = flex
    response = post_form(
        client, _url(client, "FlexMuxForm.Submit"), _flex_rows(pool_a, pool_b, prep, ["BC001", "BC001", "BC002", "BC003"]),
        token=insider_token, params=prep.params(C.MUXType.TENX_FLEX_PROBE),
    )

    assert_form_invalid(response, "'Barcode ID' is duplicated in library.")
    assert prep.mux(pool_a) == {"Smpl1": None, "Smpl2": None}


def test_flex_completion_clears_state(client: TestClient, prep: Prep, flex, insider_token: str):
    pool_a, pool_b = flex
    post_form(
        client, _url(client, "FlexMuxForm.Submit"), _flex_rows(pool_a, pool_b, prep, ["BC001", "BC002", "BC001", "BC002"]),
        token=insider_token, params=prep.params(C.MUXType.TENX_FLEX_PROBE),
    )
    r = Redis(connection_pool=client.app.state.redis_pool)  # type: ignore[attr-defined]
    assert list(r.scan_iter(f"MuxPrepWorkflow:{prep.uuid}:*")) == []


# ── Flex + ABC ──────────────────────────────────────────────────────────────


@pytest.fixture
def flex_abc(prep: Prep) -> tuple[models.Library, models.Library]:
    """PoolA: GEX and ABC Flex libraries for Smpl1, Smpl2."""
    gex = prep.library("PoolA", GEX, [prep.s1, prep.s2], C.MUXType.TENX_FLEX_PROBE)
    abc = prep.library("PoolA", ABC, [prep.s1, prep.s2], C.MUXType.TENX_FLEX_PROBE)
    return gex, abc


def _gex_rows(prep: Prep, gex: models.Library, barcodes: list[str]) -> dict[str, str]:
    return spreadsheet_payload(FLEX_COLUMNS, [
        [prep.s1.id, gex.id, "PoolA", "Smpl1", barcodes[0]],
        [prep.s2.id, gex.id, "PoolA", "Smpl2", barcodes[1]],
    ])


def _abc_rows(prep: Prep, abc: models.Library, barcodes: list[str]) -> dict[str, str]:
    return spreadsheet_payload(FLEX_COLUMNS, [
        [prep.s1.id, abc.id, "PoolA", "Smpl1", barcodes[0]],
        [prep.s2.id, abc.id, "PoolA", "Smpl2", barcodes[1]],
    ])


def _submit_gex(client: TestClient, prep: Prep, gex: models.Library, token: str, barcodes=("BC001", "BC002")):
    return post_form(client, _url(client, "FlexMuxForm.Submit"), _gex_rows(prep, gex, list(barcodes)), token=token, params=prep.params(C.MUXType.TENX_FLEX_PROBE))


def test_flex_with_abc_continues_to_abc_step(client: TestClient, prep: Prep, flex_abc, insider_token: str):
    gex, abc = flex_abc
    response = _submit_gex(client, prep, gex, insider_token)

    assert response.status_code == 200, response.text
    assert prep.mux(gex) == {"Smpl1": None, "Smpl2": None}  # saved only at the end


def test_abc_step_prefills_ab_barcodes_from_gex(client: TestClient, prep: Prep, flex_abc, insider_token: str):
    """Legacy: GEX barcode BC001 → ABC barcode AB001."""
    gex, abc = flex_abc
    response = _submit_gex(client, prep, gex, insider_token)

    assert response.status_code == 200, response.text
    assert "AB001" in response.text and "AB002" in response.text


def test_flex_abc_saves_both(client: TestClient, prep: Prep, flex_abc, insider_token: str):
    gex, abc = flex_abc
    _submit_gex(client, prep, gex, insider_token)

    response = post_form(client, _url(client, "FlexABCForm.Submit"), _abc_rows(prep, abc, ["AB003", "AB004"]), token=insider_token, params=prep.params(C.MUXType.TENX_FLEX_PROBE))

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.mux(gex) == {"Smpl1": {"barcode": "BC001"}, "Smpl2": {"barcode": "BC002"}}
    assert prep.mux(abc) == {"Smpl1": {"barcode": "AB003"}, "Smpl2": {"barcode": "AB004"}}


@pytest.mark.parametrize("barcode", ["BC001", "AB017", "AB1"])
def test_abc_barcode_outside_ab001_ab016_is_rejected(client: TestClient, prep: Prep, flex_abc, insider_token: str, barcode: str):
    gex, abc = flex_abc
    _submit_gex(client, prep, gex, insider_token)

    response = post_form(client, _url(client, "FlexABCForm.Submit"), _abc_rows(prep, abc, [barcode, "AB002"]), token=insider_token, params=prep.params(C.MUXType.TENX_FLEX_PROBE))

    assert_form_invalid(response, "'Barcode ID' must be one of")
    assert prep.mux(abc) == {"Smpl1": None, "Smpl2": None}


def test_abc_duplicate_barcode_is_rejected(client: TestClient, prep: Prep, flex_abc, insider_token: str):
    gex, abc = flex_abc
    _submit_gex(client, prep, gex, insider_token)

    response = post_form(client, _url(client, "FlexABCForm.Submit"), _abc_rows(prep, abc, ["AB001", "AB001"]), token=insider_token, params=prep.params(C.MUXType.TENX_FLEX_PROBE))

    assert_form_invalid(response, "'Barcode ID' is duplicated in library.")


def test_abc_back_navigation_keeps_gex_barcodes(client: TestClient, prep: Prep, flex_abc, insider_token: str):
    gex, abc = flex_abc
    _submit_gex(client, prep, gex, insider_token, barcodes=("BC011", "BC012"))

    response = get(client, _url(client, "FlexMuxForm.Previous"), insider_token, params=prep.params(C.MUXType.TENX_FLEX_PROBE))

    assert response.status_code == 200, response.text
    assert "BC011" in response.text and "BC012" in response.text


def test_abc_step_without_gex_step_is_400(client: TestClient, prep: Prep, flex_abc, insider_token: str):
    """The ABC step reads the GEX step's state: without it (expired / skipped) it is a controlled 400."""
    gex, abc = flex_abc
    params = prep.params(C.MUXType.TENX_FLEX_PROBE)

    assert get(client, _url(client, "FlexABCForm.Previous"), insider_token, params=params).status_code == 400
    response = post_form(client, _url(client, "FlexABCForm.Submit"), _abc_rows(prep, abc, ["AB001", "AB002"]), token=insider_token, params=params)
    assert response.status_code == 400
    assert prep.mux(abc) == {"Smpl1": None, "Smpl2": None}


# ── On-chip multiplexing ────────────────────────────────────────────────────


@pytest.fixture
def ocm(prep: Prep) -> tuple[models.Library, models.Library]:
    pool_a = prep.library("PoolA", C.LibraryType.TENX_SC_GEX_3PRIME, [prep.s1, prep.s2], C.MUXType.TENX_ON_CHIP)
    pool_b = prep.library("PoolB", C.LibraryType.TENX_SC_GEX_3PRIME, [prep.s3, prep.s4], C.MUXType.TENX_ON_CHIP)
    return pool_a, pool_b


def _ocm(client: TestClient, prep: Prep, token: str, barcodes: list[str]):
    rows = [["Smpl1", "PoolA", barcodes[0]], ["Smpl2", "PoolA", barcodes[1]], ["Smpl3", "PoolB", barcodes[2]], ["Smpl4", "PoolB", barcodes[3]]]
    return post_form(client, _url(client, "OCMMuxForm.Submit"), spreadsheet_payload(OCM_COLUMNS, rows), token=token, params=prep.params(C.MUXType.TENX_ON_CHIP))


def test_ocm_begin_lists_samples(client: TestClient, prep: Prep, ocm, insider_token: str):
    response = get(client, _url(client, "Begin"), insider_token, params=prep.params(C.MUXType.TENX_ON_CHIP))

    assert response.status_code == 200, response.text
    for text in ("Smpl1", "Smpl4", "PoolA", "PoolB"):
        assert text in response.text


def test_ocm_saves_normalized_barcodes(client: TestClient, prep: Prep, ocm, insider_token: str):
    pool_a, pool_b = ocm
    response = _ocm(client, prep, insider_token, ["1", "OB2", "2;1", " 3 "])

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.mux(pool_a) == {"Smpl1": {"barcode": "OB1"}, "Smpl2": {"barcode": "OB2"}}
    assert prep.mux(pool_b) == {"Smpl3": {"barcode": "OB1;OB2"}, "Smpl4": {"barcode": "OB3"}}


@pytest.mark.parametrize("barcode", ["OB5", "9"])
def test_ocm_invalid_barcode_is_rejected(client: TestClient, prep: Prep, ocm, insider_token: str, barcode: str):
    pool_a, _ = ocm
    response = _ocm(client, prep, insider_token, [barcode, "OB2", "OB1", "OB2"])

    assert_form_invalid(response, "'Barcode ID' must be one of: OB1, OB2, OB3, OB4")
    assert prep.mux(pool_a) == {"Smpl1": None, "Smpl2": None}


def test_ocm_duplicate_barcode_in_pool_is_rejected(client: TestClient, prep: Prep, ocm, insider_token: str):
    response = _ocm(client, prep, insider_token, ["OB1", "OB1", "OB1", "OB2"])

    assert_form_invalid(response, "'Barcode ID' is duplicated in library.")


def test_ocm_missing_barcode_is_rejected(client: TestClient, prep: Prep, ocm, insider_token: str):
    response = _ocm(client, prep, insider_token, ["", "OB1", "OB1", "OB2"])

    assert_form_invalid(response)


# ── Oligo multiplexing ──────────────────────────────────────────────────────


@pytest.fixture
def oligo(prep: Prep) -> models.Library:
    return prep.library("PoolA", C.LibraryType.TENX_SC_GEX_3PRIME, [prep.s1, prep.s2], C.MUXType.TENX_OLIGO)


@pytest.fixture
def cmo_kit(session: SyncSession) -> models.FeatureKit:
    kit = create_feature_kit(session)
    kit.type = C.FeatureType.CMO
    session.save(kit, flush=True)
    for name, sequence in (("CMO301", "ATGAGGAATTCCTGC"), ("CMO302", "CATGCCAATAGAGCG")):
        feature = create_feature(session, kit)
        feature.name, feature.sequence, feature.pattern, feature.read = name, sequence, PATTERN, "R2"
        session.save(feature, flush=True)
    session.commit()
    return kit


def _oligo(client: TestClient, prep: Prep, token: str, rows: list[list[str]]):
    payload = spreadsheet_payload(OLIGO_COLUMNS, [[f"Smpl{i + 1}", "PoolA", *row] for i, row in enumerate(rows)])
    return post_form(client, _url(client, "OligoMuxForm.Submit"), payload, token=token, params=prep.params(C.MUXType.TENX_OLIGO))


def _kit_label(kit: models.FeatureKit) -> str:
    return f"[{kit.identifier}] {kit.name}"


def test_oligo_begin_lists_samples_and_cmo_kits(client: TestClient, prep: Prep, oligo, cmo_kit, insider_token: str):
    response = get(client, _url(client, "Begin"), insider_token, params=prep.params(C.MUXType.TENX_OLIGO))

    assert response.status_code == 200, response.text
    assert "Smpl1" in response.text and "Smpl2" in response.text
    assert _kit_label(cmo_kit) in response.text


def test_oligo_custom_sequences_are_saved(client: TestClient, prep: Prep, oligo, insider_token: str):
    response = _oligo(client, prep, insider_token, [
        ["", "", "AAAACCCCGGGG", PATTERN, "R2"],
        ["", "", "TTTTGGGGCCCC", PATTERN, "R1"],
    ])

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.mux(oligo) == {
        "Smpl1": {"barcode": "AAAACCCCGGGG", "pattern": PATTERN, "read": "R2"},
        "Smpl2": {"barcode": "TTTTGGGGCCCC", "pattern": PATTERN, "read": "R1"},
    }


def test_oligo_kit_feature_fills_sequence(client: TestClient, prep: Prep, oligo, cmo_kit, insider_token: str):
    response = _oligo(client, prep, insider_token, [
        [_kit_label(cmo_kit), "CMO301", "", "", ""],
        [_kit_label(cmo_kit), "CMO302", "", "", ""],
    ])

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.mux(oligo) == {
        "Smpl1": {"barcode": "ATGAGGAATTCCTGC", "pattern": PATTERN, "read": "R2"},
        "Smpl2": {"barcode": "CATGCCAATAGAGCG", "pattern": PATTERN, "read": "R2"},
    }


@pytest.mark.parametrize("row, message", [
    (["", "", "", "", ""], "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."),
    (["", "", "AAAACCCCGGGG", "", ""], "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."),
    (["KIT", "CMO301", "AAAACCCCGGGG", PATTERN, "R2"], "not both."),
    (["KIT", "CMO999", "", "", ""], "Feature 'CMO999' not found in kit"),
])
def test_oligo_invalid_definitions_are_rejected(
    client: TestClient, prep: Prep, oligo, cmo_kit, insider_token: str, row: list[str], message: str,
):
    row = [_kit_label(cmo_kit) if cell == "KIT" else cell for cell in row]
    response = _oligo(client, prep, insider_token, [row, ["", "", "TTTTGGGGCCCC", PATTERN, "R1"]])

    assert_form_invalid(response, message)
    assert prep.mux(oligo) == {"Smpl1": None, "Smpl2": None}


def test_oligo_duplicate_definition_in_pool_is_rejected(client: TestClient, prep: Prep, oligo, insider_token: str):
    response = _oligo(client, prep, insider_token, [
        ["", "", "AAAACCCCGGGG", PATTERN, "R2"],
        ["", "", "AAAACCCCGGGG", PATTERN, "R2"],
    ])

    assert_form_invalid(response, "Definitions must be unique for each sample.")
