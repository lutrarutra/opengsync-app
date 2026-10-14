"""SamplePoolingAction: regroup a lab prep's multiplexed samples into libraries.

The spreadsheet lists one row per (sample, pool) of the lab prep's multiplexed libraries
(pool = ``Library.sample_name``). On submit, each (pool, library type) becomes a library
``{pool}_{library type identifier}`` and samples are linked keeping their mux barcode.
Non-multiplexed libraries are not touched.

Legacy deleted every library and re-created one per (pool, old library), copying the old
library's properties and features. Here existing libraries are re-used: the library already
in the pool keeps it, a library whose pool disappeared is renamed into a new pool of the same
type (most shared samples first), and only the remaining pools get a new library copied from
an old one. Libraries left without a pool are deleted.

Unlike legacy, which keyed rows by sample and merged a sample's pools into one, a sample
may be listed in several pools: rows can be added to pool a sample into more libraries
(the barcode is copied from its other links of that library type, which must agree) and
removed to take it out of one. Every sample needs at least one row.

Samples are no longer failed here (pool ``x`` is refused): that is RejectSamplesAction.
REJECTED samples are listed and pooled like any other sample.

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
COLUMNS = ["Sample", "Pool"]
GEX = C.LibraryType.TENX_SC_GEX_FLEX
ABC = C.LibraryType.TENX_SC_ABC_FLEX


def _path(lab_prep_id: int) -> str:
    return f"{PREFIX}/{lab_prep_id}"


def _payload(pools: dict[models.Sample, str]) -> dict[str, str]:
    return _rows([(sample, pool) for sample, pool in pools.items()])


def _rows(rows: list[tuple[models.Sample, str]]) -> dict[str, str]:
    return spreadsheet_payload(COLUMNS, [[_label(sample), pool] for sample, pool in rows])


def _label(sample: models.Sample) -> str:
    """The sample's option in the Sample column, rejected samples are marked."""
    if sample.status == C.SampleStatus.REJECTED:
        return f"{sample.name} ⛔ [{sample.id}]"
    return f"{sample.name} [{sample.id}]"


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


def test_pool_x_is_refused(client: TestClient, prep: Prep, insider_token: str):
    before = prep.layout()

    for pool in ("x", "X"):
        response = _submit(client, prep, insider_token, S2=pool)

        assert_form_invalid(response)
        assert "Reject Samples" in response.text
    assert prep.layout() == before
    assert {lib.id for lib in prep.libraries().values()} == {prep.pool_a.id, prep.pool_b.id}


def test_render_lists_rejected_samples(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    prep.s2.status = C.SampleStatus.REJECTED
    session.save(prep.s2, flush=True)
    session.commit()

    response = get(client, _path(prep.lab_prep.id), insider_token)

    assert response.status_code == 200
    assert f"['{_label(prep.s2)}', 'PoolA']" in response.text
    assert "S2 ⛔" in response.text


def test_rejected_samples_are_pooled_like_any_other(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    prep.s2.status = C.SampleStatus.REJECTED
    session.save(prep.s2, flush=True)
    session.commit()

    response = _submit(client, prep, insider_token, S2="PoolB")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.layout() == {
        "PoolA_10XFLEXGEX": {"S1": "BC_S1"},
        "PoolB_10XFLEXGEX": {"S2": "BC_S2", "S3": "BC_S3", "S4": "BC_S4"},
    }
    assert prep.s2.status == C.SampleStatus.REJECTED


def test_rejected_sample_needs_a_pool(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    prep.s2.status = C.SampleStatus.REJECTED
    session.save(prep.s2, flush=True)
    session.commit()
    before = prep.layout()
    pools = prep.pools()
    del pools[prep.s2]

    response = post_form(client, _path(prep.lab_prep.id), _payload(pools), token=insider_token)

    assert_form_invalid(response)
    assert "missing: S2" in response.text
    assert prep.layout() == before


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



def test_sample_of_another_lab_prep_is_rejected(
    client: TestClient, session: SyncSession, prep: Prep, user, insider, insider_token: str,
):
    other = Prep(session, user, insider)
    session.commit()
    before, other_before = prep.layout(), other.layout()
    pools = prep.pools()
    pools[other.s1] = "PoolA"

    response = post_form(client, _path(prep.lab_prep.id), _payload(pools), token=insider_token)

    assert_form_invalid(response)
    assert prep.layout() == before
    assert other.layout() == other_before


def test_missing_sample_is_rejected(client: TestClient, prep: Prep, insider_token: str):
    before = prep.layout()
    pools = prep.pools()
    del pools[prep.s2]

    response = post_form(client, _path(prep.lab_prep.id), _payload(pools), token=insider_token)

    assert_form_invalid(response)
    assert "missing: S2" in response.text
    assert prep.layout() == before


def test_non_multiplexed_sample_is_rejected(
    client: TestClient, session: SyncSession, prep: Prep, user, insider_token: str,
):
    sample = create_sample(session, user, create_project(session, user))
    sample.name = "PlainSample"
    prep.library("PlainPool", C.LibraryType.BULK_RNA_SEQ, [sample], mux_type=None)
    session.commit()
    before = prep.layout()
    pools = prep.pools()
    pools[sample] = "PoolA"

    response = post_form(client, _path(prep.lab_prep.id), _payload(pools), token=insider_token)

    assert_form_invalid(response)
    assert prep.layout() == before


# ── Submit: a sample in several pools ───────────────────────────────────────


def test_sample_in_two_pools_keeps_both(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    """Legacy keyed rows by sample and merged S1's pools into one."""
    actions.link_sample_library(session, prep.s1.id, prep.pool_b.id, mux={"barcode": "BC_S1_B"})
    session.commit()
    rows = [(prep.s1, "PoolA"), (prep.s1, "PoolB"), (prep.s2, "PoolA"), (prep.s3, "PoolB"), (prep.s4, "PoolB")]

    response = post_form(client, _path(prep.lab_prep.id), _rows(rows), token=insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.layout() == {
        "PoolA_10XFLEXGEX": {"S1": "BC_S1", "S2": "BC_S2"},
        "PoolB_10XFLEXGEX": {"S1": "BC_S1_B", "S3": "BC_S3", "S4": "BC_S4"},
    }


def test_render_lists_a_sample_once_per_pool(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    actions.link_sample_library(session, prep.s1.id, prep.pool_b.id, mux={"barcode": "BC_S1"})
    session.commit()

    response = get(client, _path(prep.lab_prep.id), insider_token)

    assert response.status_code == 200
    for pool in ("PoolA", "PoolB"):
        assert f"['{_label(prep.s1)}', '{pool}']" in response.text


def test_adding_a_row_pools_a_sample_into_another_library(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    prep.library("PoolA", ABC, [prep.s1, prep.s2])
    prep.library("PoolB", ABC, [prep.s3, prep.s4])
    session.commit()
    rows = list(prep.pools().items()) + [(prep.s1, "PoolC")]

    response = post_form(client, _path(prep.lab_prep.id), _rows(rows), token=insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.layout() == {
        "PoolA_10XFLEXGEX": {"S1": "BC_S1", "S2": "BC_S2"},
        "PoolB_10XFLEXGEX": {"S3": "BC_S3", "S4": "BC_S4"},
        "PoolC_10XFLEXGEX": {"S1": "BC_S1"},
        "PoolA_10XFLEXABC": {"S1": "BC_S1", "S2": "BC_S2"},
        "PoolB_10XFLEXABC": {"S3": "BC_S3", "S4": "BC_S4"},
        "PoolC_10XFLEXABC": {"S1": "BC_S1"},
    }
    assert prep.libraries()["PoolC_10XFLEXGEX"].sample_name == "PoolC"


def test_removing_a_row_takes_a_sample_out_of_one_pool(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    actions.link_sample_library(session, prep.s1.id, prep.pool_b.id, mux={"barcode": "BC_S1"})
    session.commit()

    response = _submit(client, prep, insider_token)

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert prep.layout() == {
        "PoolA_10XFLEXGEX": {"S1": "BC_S1", "S2": "BC_S2"},
        "PoolB_10XFLEXGEX": {"S3": "BC_S3", "S4": "BC_S4"},
    }


def test_new_pool_with_conflicting_barcodes_is_rejected(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    actions.link_sample_library(session, prep.s1.id, prep.pool_b.id, mux={"barcode": "BC_S1_B"})
    session.commit()
    before = prep.layout()
    rows = [(prep.s1, "PoolA"), (prep.s1, "PoolC"), (prep.s2, "PoolA"), (prep.s3, "PoolB"), (prep.s4, "PoolB")]

    response = post_form(client, _path(prep.lab_prep.id), _rows(rows), token=insider_token)

    assert_form_invalid(response)
    assert "different barcodes" in response.text
    assert prep.layout() == before


def test_duplicate_sample_pool_row_is_rejected(client: TestClient, prep: Prep, insider_token: str):
    before = prep.layout()
    rows = list(prep.pools().items()) + [(prep.s1, "PoolA")]

    response = post_form(client, _path(prep.lab_prep.id), _rows(rows), token=insider_token)

    assert_form_invalid(response)
    assert prep.layout() == before


# ── Submit: re-using libraries ──────────────────────────────────────────────


def _library_ids(prep: Prep) -> dict[str, int]:
    return {name: library.id for name, library in prep.libraries().items()}


def test_moving_a_sample_keeps_the_libraries(client: TestClient, prep: Prep, insider_token: str):
    response = _submit(client, prep, insider_token, S2="PoolB")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert _library_ids(prep) == {"PoolA_10XFLEXGEX": prep.pool_a.id, "PoolB_10XFLEXGEX": prep.pool_b.id}


def test_renaming_a_pool_renames_its_library(client: TestClient, prep: Prep, insider_token: str):
    response = _submit(client, prep, insider_token, S3="PoolC", S4="PoolC")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert _library_ids(prep) == {"PoolA_10XFLEXGEX": prep.pool_a.id, "PoolC_10XFLEXGEX": prep.pool_b.id}
    assert prep.libraries()["PoolC_10XFLEXGEX"].sample_name == "PoolC"
    assert prep.layout()["PoolC_10XFLEXGEX"] == {"S3": "BC_S3", "S4": "BC_S4"}


def test_swapping_pools_keeps_the_libraries_with_the_most_samples(client: TestClient, prep: Prep, insider_token: str):
    """PoolA and PoolB disappear: PoolC takes PoolB's library (S3, S4 move together), PoolD takes PoolA's."""
    response = _submit(client, prep, insider_token, S1="PoolD", S2="PoolC", S3="PoolC", S4="PoolC")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert _library_ids(prep) == {"PoolC_10XFLEXGEX": prep.pool_b.id, "PoolD_10XFLEXGEX": prep.pool_a.id}
    assert prep.layout() == {
        "PoolC_10XFLEXGEX": {"S2": "BC_S2", "S3": "BC_S3", "S4": "BC_S4"},
        "PoolD_10XFLEXGEX": {"S1": "BC_S1"},
    }


def test_merging_pools_keeps_the_library_of_the_remaining_pool(client: TestClient, prep: Prep, insider_token: str):
    response = _submit(client, prep, insider_token, S3="PoolA", S4="PoolA")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    assert _library_ids(prep) == {"PoolA_10XFLEXGEX": prep.pool_a.id}


def test_splitting_a_pool_keeps_its_library(client: TestClient, prep: Prep, insider_token: str):
    response = _submit(client, prep, insider_token, S4="PoolC")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    ids = _library_ids(prep)
    assert ids["PoolA_10XFLEXGEX"] == prep.pool_a.id
    assert ids["PoolB_10XFLEXGEX"] == prep.pool_b.id
    assert ids["PoolC_10XFLEXGEX"] not in (prep.pool_a.id, prep.pool_b.id)


def test_library_is_only_re_used_for_its_own_type(
    client: TestClient, session: SyncSession, prep: Prep, insider_token: str,
):
    abc_b = prep.library("PoolB", ABC, [prep.s3, prep.s4])
    session.commit()

    response = _submit(client, prep, insider_token, S3="PoolC", S4="PoolC")

    assert_htmx_redirect(response, f"/lab_preps/{prep.lab_prep.id}")
    ids = _library_ids(prep)
    assert ids["PoolC_10XFLEXGEX"] == prep.pool_b.id
    assert ids["PoolC_10XFLEXABC"] == abc_b.id
