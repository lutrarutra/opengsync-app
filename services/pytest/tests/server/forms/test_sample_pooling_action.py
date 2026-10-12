"""SamplePoolingAction: regroup a lab prep's multiplexed samples into libraries.

The spreadsheet lists every sample of the lab prep's multiplexed libraries with its
current pool (``Library.sample_name``). On submit, as legacy
``mux_prep_workflow.sample_pooling``: each (pool, old library) group becomes a new
library ``{pool}_{library type identifier}`` that copies the old library's properties
and features, samples are re-linked keeping their mux barcode, pool ``x`` collects
cancelled samples in a FAILED ``canceled_samples_{type}`` library, and libraries left
without samples are deleted. Non-multiplexed libraries are not touched.

Access is insider-only. Legacy had no role check on this route (login only); lab preps
are insider-only everywhere else, so the stricter FastAPI check is kept.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models, queries as Q, categories as C, actions

from ...db.create_units import (
    create_feature, create_lab_prep, create_library, create_project, create_sample, create_seq_request,
)
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
    spreadsheet_payload,
)

PREFIX = "/htmx/actions/sample-pooling"
COLUMNS = ["Sample ID", "Sample Name", "Pool"]
GEX = C.LibraryType.TENX_SC_GEX_FLEX
ABC = C.LibraryType.TENX_SC_ABC_FLEX


def _path(lab_prep_id: int) -> str:
    return f"{PREFIX}/{lab_prep_id}"


def _payload(pools: dict[models.Sample, str]) -> dict[str, str]:
    return spreadsheet_payload(COLUMNS, [[sample.id, sample.name, pool] for sample, pool in pools.items()])


class Prep:
    """A lab prep with two multiplexed Flex GEX libraries: PoolA (s1, s2) and PoolB (s3, s4)."""

    def __init__(self, session: SyncSession, user: models.User, insider: models.User):
        self.session = session
        self.user = user
        self.lab_prep = create_lab_prep(session, insider)
        self.seq_request = create_seq_request(session, user)
        project = create_project(session, user)
        self.samples = [create_sample(session, user, project) for _ in range(4)]
        for i, sample in enumerate(self.samples, start=1):
            sample.name = f"S{i}"
        self.s1, self.s2, self.s3, self.s4 = self.samples
        self.pool_a = self.library("PoolA", GEX, [self.s1, self.s2])
        self.pool_b = self.library("PoolB", GEX, [self.s3, self.s4])

    def library(
        self, pool: str, library_type, samples: list[models.Sample], mux_type=C.MUXType.TENX_FLEX_PROBE,
    ) -> models.Library:
        library = create_library(self.session, self.user, self.seq_request)
        library.name = f"{pool}_{library_type.identifier}"
        library.sample_name = pool
        library.type = library_type
        library.mux_type = mux_type
        library.lab_prep_id = self.lab_prep.id
        library.status = C.LibraryStatus.ACCEPTED
        library.genome_ref = C.GenomeRef.HUMAN
        self.session.save(library, flush=True)
        for sample in samples:
            actions.link_sample_library(self.session, sample.id, library.id, mux={"barcode": f"BC_{sample.name}"})
        return library

    def pools(self, **overrides: str) -> dict[models.Sample, str]:
        """Current pools, with ``S2="PoolB"``-style overrides."""
        current = {self.s1: "PoolA", self.s2: "PoolA", self.s3: "PoolB", self.s4: "PoolB"}
        return {sample: overrides.get(sample.name, pool) for sample, pool in current.items()}

    def libraries(self) -> dict[str, models.Library]:
        self.session.expire_all()
        libraries = self.session.get_all(Q.library.select(lab_prep_id=self.lab_prep.id), limit=None)
        return {library.name: library for library in libraries}

    def layout(self) -> dict[str, dict[str, Any]]:
        """Library name → its samples and their mux barcodes."""
        return {
            name: {link.sample.name: (link.mux or {}).get("barcode") for link in library.sample_links}
            for name, library in self.libraries().items()
        }


@pytest.fixture
def prep(session: SyncSession, user, insider) -> Prep:
    prep = Prep(session, user, insider)
    session.commit()
    return prep


def _submit(client: TestClient, prep: Prep, token: str, **overrides: str):
    return post_form(client, _path(prep.lab_prep.id), _payload(prep.pools(**overrides)), token=token)


# ── Render (GET) ────────────────────────────────────────────────────────────


def test_render_lists_samples_and_pools(client: TestClient, prep: Prep, insider_token: str):
    response = get(client, _path(prep.lab_prep.id), insider_token)

    assert response.status_code == 200
    assert 'name="csrf_token"' in response.text
    for text in ("S1", "S2", "S3", "S4", "PoolA", "PoolB"):
        assert text in response.text


def test_render_omits_non_multiplexed_libraries(
    client: TestClient, session: SyncSession, prep: Prep, user, insider_token: str,
):
    sample = create_sample(session, user, create_project(session, user))
    sample.name = "PlainSample"
    prep.library("PlainPool", C.LibraryType.BULK_RNA_SEQ, [sample], mux_type=None)
    session.commit()

    response = get(client, _path(prep.lab_prep.id), insider_token)

    assert response.status_code == 200
    assert "PlainSample" not in response.text


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_is_denied(client: TestClient, prep: Prep, user_token: str):
    assert get(client, _path(prep.lab_prep.id), user_token).status_code == 403
    assert _submit(client, prep, user_token, S2="PoolB").status_code == 403
    assert set(prep.layout()) == {"PoolA_10XFLEXGEX", "PoolB_10XFLEXGEX"}


def test_anonymous_is_redirected_to_login(client: TestClient, prep: Prep):
    for response in (get(client, _path(prep.lab_prep.id)), post_form(client, _path(prep.lab_prep.id), {})):
        assert response.status_code == 303
        assert "/auth/login" in response.headers.get("location", "")


def test_unknown_lab_prep_is_404(client: TestClient, insider_token: str):
    assert get(client, _path(999999), insider_token).status_code == 404


def test_csrf_mismatch_changes_nothing(client: TestClient, prep: Prep, insider_token: str):
    before = prep.layout()
    response = post_form_csrf_mismatch(
        client, _path(prep.lab_prep.id), _payload(prep.pools(S2="PoolB")), token=insider_token,
    )
    assert response.status_code != 204
    assert prep.layout() == before
    assert {lib.id for lib in prep.libraries().values()} == {prep.pool_a.id, prep.pool_b.id}


# ── Submit: regrouping ──────────────────────────────────────────────────────


def test_unchanged_pools_keep_the_layout(client: TestClient, prep: Prep, insider_token: str):
    response = _submit(client, prep, insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert_flash(response, "Sample pool annotation processed successfully.", category="success")
    assert prep.layout() == {
        "PoolA_10XFLEXGEX": {"S1": "BC_S1", "S2": "BC_S2"},
        "PoolB_10XFLEXGEX": {"S3": "BC_S3", "S4": "BC_S4"},
    }


def test_moving_a_sample_to_another_pool(client: TestClient, prep: Prep, insider_token: str):
    response = _submit(client, prep, insider_token, S2="PoolB")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.layout() == {
        "PoolA_10XFLEXGEX": {"S1": "BC_S1"},
        "PoolB_10XFLEXGEX": {"S2": "BC_S2", "S3": "BC_S3", "S4": "BC_S4"},
    }


def test_new_pool_name_creates_a_library(client: TestClient, prep: Prep, insider_token: str):
    response = _submit(client, prep, insider_token, S4="PoolC")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.layout() == {
        "PoolA_10XFLEXGEX": {"S1": "BC_S1", "S2": "BC_S2"},
        "PoolB_10XFLEXGEX": {"S3": "BC_S3"},
        "PoolC_10XFLEXGEX": {"S4": "BC_S4"},
    }
    assert prep.libraries()["PoolC_10XFLEXGEX"].sample_name == "PoolC"


def test_emptied_pool_library_is_deleted(client: TestClient, prep: Prep, insider_token: str):
    response = _submit(client, prep, insider_token, S3="PoolA", S4="PoolA")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.layout() == {"PoolA_10XFLEXGEX": {"S1": "BC_S1", "S2": "BC_S2", "S3": "BC_S3", "S4": "BC_S4"}}


def test_pool_x_cancels_samples_into_a_failed_library(client: TestClient, prep: Prep, insider_token: str):
    response = _submit(client, prep, insider_token, S2="x")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.layout() == {
        "PoolA_10XFLEXGEX": {"S1": "BC_S1"},
        "PoolB_10XFLEXGEX": {"S3": "BC_S3", "S4": "BC_S4"},
        "canceled_samples_10XFLEXGEX": {"S2": "BC_S2"},
    }
    libraries = prep.libraries()
    assert libraries["canceled_samples_10XFLEXGEX"].status == C.LibraryStatus.FAILED
    assert libraries["PoolA_10XFLEXGEX"].status == C.LibraryStatus.ACCEPTED


def test_new_libraries_copy_the_old_library(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    feature = create_feature(session)
    prep.pool_a.features.append(feature)
    session.save(prep.pool_a, flush=True)
    session.commit()

    response = _submit(client, prep, insider_token, S4="PoolC")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    libraries = prep.libraries()
    for name in ("PoolA_10XFLEXGEX", "PoolC_10XFLEXGEX"):
        library = libraries[name]
        assert library.type == GEX
        assert library.mux_type == C.MUXType.TENX_FLEX_PROBE
        assert library.status == C.LibraryStatus.ACCEPTED
        assert library.genome_ref == C.GenomeRef.HUMAN
        assert library.owner_id == prep.user.id
        assert library.seq_request_id == prep.seq_request.id
        assert library.lab_prep_id == prep.lab_prep.id
    assert [f.id for f in libraries["PoolA_10XFLEXGEX"].features] == [feature.id]


def test_every_library_type_of_a_pool_follows_the_sample(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    """A sample in a pool's GEX and ABC libraries moves in both."""
    prep.library("PoolA", ABC, [prep.s1, prep.s2])
    prep.library("PoolB", ABC, [prep.s3, prep.s4])
    session.commit()

    response = _submit(client, prep, insider_token, S2="PoolB")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.layout() == {
        "PoolA_10XFLEXGEX": {"S1": "BC_S1"},
        "PoolB_10XFLEXGEX": {"S2": "BC_S2", "S3": "BC_S3", "S4": "BC_S4"},
        "PoolA_10XFLEXABC": {"S1": "BC_S1"},
        "PoolB_10XFLEXABC": {"S2": "BC_S2", "S3": "BC_S3", "S4": "BC_S4"},
    }


def test_non_multiplexed_libraries_are_untouched(
    client: TestClient, session: SyncSession, prep: Prep, user, insider_token: str,
):
    sample = create_sample(session, user, create_project(session, user))
    sample.name = "PlainSample"
    plain = prep.library("PlainPool", C.LibraryType.BULK_RNA_SEQ, [sample], mux_type=None)
    plain_id, plain_name = plain.id, plain.name
    session.commit()

    response = _submit(client, prep, insider_token, S2="PoolB")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    libraries = prep.libraries()
    assert libraries[plain_name].id == plain_id
    assert [link.sample.name for link in libraries[plain_name].sample_links] == ["PlainSample"]


def test_other_lab_preps_are_untouched(
    client: TestClient, session: SyncSession, prep: Prep, user, insider, insider_token: str,
):
    other = Prep(session, user, insider)
    session.commit()
    before = other.layout()

    assert_htmx_redirect(_submit(client, prep, insider_token, S2="PoolB"), f"/lab_preps/{prep.lab_prep.id}")

    assert other.layout() == before
    assert {lib.id for lib in other.libraries().values()} == {other.pool_a.id, other.pool_b.id}


# ── Submit: validation ──────────────────────────────────────────────────────


def test_missing_pool_is_rejected(client: TestClient, prep: Prep, insider_token: str):
    before = prep.layout()

    response = _submit(client, prep, insider_token, S2="")

    assert_form_invalid(response)
    assert prep.layout() == before
    assert {lib.id for lib in prep.libraries().values()} == {prep.pool_a.id, prep.pool_b.id}
