"""ReindexWorkflow barcode match: custom barcodes get the same orientation handling as library annotation."""

import json
import uuid

import pytest

from opengsync_db import SyncSession, models, categories as C, queries as Q

from ...db.create_units import create_library, create_seq_request
from .._http import OpenGSyncTestClient, post_form, spreadsheet_payload


REINDEX_PREFIX = "/htmx/workflows/reindex"
BARCODE_COLUMNS = [
    "Library", "Index Well", "i7 Kit", "i7 Name", "i7 Sequence",
    "i5 Kit", "i5 Name", "i5 Sequence",
]
PRIMER = "AATGATACGGCGACCACCGA"
I7 = "ACGTACGTAA"
I5 = "GGTTCCAACA"


def _reindex_to_barcode_match(
    client: OpenGSyncTestClient, token: str, seq_request: models.SeqRequest, library: models.Library,
    sequence_i5: str = "",
) -> dict[str, object]:
    params = {"uuid": str(uuid.uuid4()), "seq_request_id": seq_request.id}
    response = post_form(
        client, f"{REINDEX_PREFIX}/select-samples",
        {"selected_library_ids": json.dumps([library.id])},
        token=token, params=params,
    )
    assert response.status_code == 200, response.text
    response = post_form(
        client, f"{REINDEX_PREFIX}/barcode-input",
        spreadsheet_payload(BARCODE_COLUMNS, [[f"{library.name} [{library.id}]", "", "", "i7_custom", I7, "", "i5_custom" if sequence_i5 else "", sequence_i5]]),
        token=token, params=params,
    )
    assert response.status_code == 200, response.text
    assert f"{REINDEX_PREFIX}/barcode-match" in response.text
    return params


def _complete(client: OpenGSyncTestClient, token: str, params: dict[str, object], match: dict[str, str]) -> None:
    response = post_form(client, f"{REINDEX_PREFIX}/barcode-match", match, token=token, params=params)
    assert response.status_code == 200, response.text
    response = post_form(client, f"{REINDEX_PREFIX}/complete-reindex", {}, token=token, params=params)
    assert response.status_code == 204, response.text
    assert "HX-Redirect" in response.headers


@pytest.mark.parametrize("option, expected_i7", [
    ("forward", I7),
    ("rc", models.Barcode.reverse_complement(I7)),
])
def test_reindex_custom_single_index_sets_orientation(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str, option: str, expected_i7: str,
):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()

    params = _reindex_to_barcode_match(client, user_token, seq_request, library)
    _complete(client, user_token, params, {"i7_kit": "0", "i7_option": option, "i7_primer": PRIMER})

    session.expire_all()
    library = session.get_one(Q.library.select(id=library.id))
    assert [(i.name_i7, i.sequence_i7) for i in library.indices] == [("i7_custom", expected_i7)]
    assert library.indices[0].orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED


def test_reindex_custom_dual_index_rc_sets_orientation(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str,
):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()

    params = _reindex_to_barcode_match(client, user_token, seq_request, library, sequence_i5=I5)
    _complete(client, user_token, params, {
        "i7_kit": "0", "i7_option": "rc", "i7_primer": PRIMER,
        "i5_kit": "0", "i5_option": "rc", "i5_primer": PRIMER,
    })

    session.expire_all()
    library = session.get_one(Q.library.select(id=library.id))
    assert [(i.sequence_i7, i.sequence_i5) for i in library.indices] == [
        (models.Barcode.reverse_complement(I7), models.Barcode.reverse_complement(I5)),
    ]
    assert library.indices[0].orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED


def test_reindex_custom_idk_leaves_orientation_unset(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str,
):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()

    params = _reindex_to_barcode_match(client, user_token, seq_request, library)
    _complete(client, user_token, params, {"i7_kit": "0", "i7_option": "idk", "i7_primer": PRIMER})

    session.expire_all()
    library = session.get_one(Q.library.select(id=library.id))
    assert [i.sequence_i7 for i in library.indices] == [I7]
    assert library.indices[0].orientation is None


def test_reindex_custom_requires_option_and_primer(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str,
):
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()

    params = _reindex_to_barcode_match(client, user_token, seq_request, library)
    response = post_form(client, f"{REINDEX_PREFIX}/barcode-match", {"i7_kit": "0"}, token=user_token, params=params)
    assert response.status_code != 200 or f"{REINDEX_PREFIX}/complete-reindex" not in response.text
    assert "Please select how to proceed with the i7 index." in response.text
    assert "Please provide the i7 primer sequence." in response.text


def _kit(session: SyncSession, type: C.IndexType, adapters: list[list[tuple[C.BarcodeType, str]]]) -> models.IndexKit:
    """Index kit with one adapter per entry; barcodes are named KIT_<type>_<n>."""
    _uuid = str(uuid.uuid4())
    kit = session.save(Q.index_kit.create(name=_uuid, identifier=_uuid[:12], type=type, supported_protocol_ids=[]), flush=True)
    for n, barcodes in enumerate(adapters):
        well = None if type == C.IndexType.COMBINATORIAL_DUAL_INDEX else f"A{n + 1}"
        adapter = session.save(Q.adapter.create(index_kit=kit, well=well), flush=True)
        for barcode_type, sequence in barcodes:
            session.save(Q.barcode.create(
                name=f"KIT_{barcode_type.name}_{n}", sequence=sequence, well=well, type=barcode_type, adapter=adapter,
            ), flush=True)
    session.commit()
    return kit


@pytest.mark.parametrize("kit_type, adapters", [
    (C.IndexType.DUAL_INDEX, [[(C.BarcodeType.INDEX_I7, I7), (C.BarcodeType.INDEX_I5, I5)]]),
    # i5 shared between adapters
    (C.IndexType.DUAL_INDEX, [
        [(C.BarcodeType.INDEX_I7, I7), (C.BarcodeType.INDEX_I5, I5)],
        [(C.BarcodeType.INDEX_I7, "TTTTCCCCGG"), (C.BarcodeType.INDEX_I5, I5)],
    ]),
    (C.IndexType.COMBINATORIAL_DUAL_INDEX, [
        [(C.BarcodeType.INDEX_I7, I7)], [(C.BarcodeType.INDEX_I7, "TTTTCCCCGG")],
        [(C.BarcodeType.INDEX_I5, I5)], [(C.BarcodeType.INDEX_I5, "CCCCAAAAGG")],
    ]),
])
def test_reindex_kit_selected(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str, kit_type, adapters,
):
    kit = _kit(session, kit_type, adapters)
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()

    params = _reindex_to_barcode_match(client, user_token, seq_request, library, sequence_i5=I5)
    _complete(client, user_token, params, {"i7_kit": str(kit.id), "i5_kit": str(kit.id)})

    session.expire_all()
    library = session.get_one(Q.library.select(id=library.id))
    assert [(i.sequence_i7, i.sequence_i5) for i in library.indices] == [(I7, I5)]
    assert library.indices[0].orientation == C.BarcodeOrientation.FORWARD


def test_reindex_kit_not_offered_is_rejected(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str,
):
    """Regression: a kit id that was not offered crashed the submit (KeyError) instead of a form error."""
    unrelated = _kit(session, C.IndexType.DUAL_INDEX, [[(C.BarcodeType.INDEX_I7, "TTTTCCCCGG"), (C.BarcodeType.INDEX_I5, I5)]])
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()

    params = _reindex_to_barcode_match(client, user_token, seq_request, library, sequence_i5=I5)
    response = post_form(client, f"{REINDEX_PREFIX}/barcode-match", {
        "i7_kit": str(unrelated.id), "i5_kit": str(unrelated.id),
    }, token=user_token, params=params)

    assert f"{REINDEX_PREFIX}/complete-reindex" not in response.text
    assert "The selected kit does not contain all i7 sequences." in response.text
    assert "The selected kit does not contain all i5 sequences." not in response.text


def test_reindex_reverse_complement_kit(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str,
):
    rc_i7, rc_i5 = models.Barcode.reverse_complement(I7), models.Barcode.reverse_complement(I5)
    kit = _kit(session, C.IndexType.DUAL_INDEX, [[(C.BarcodeType.INDEX_I7, rc_i7), (C.BarcodeType.INDEX_I5, rc_i5)]])
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()

    params = _reindex_to_barcode_match(client, user_token, seq_request, library, sequence_i5=I5)
    _complete(client, user_token, params, {"i7_kit": f"{kit.id}:rc", "i5_kit": f"{kit.id}:rc"})

    session.expire_all()
    library = session.get_one(Q.library.select(id=library.id))
    assert [(i.sequence_i7, i.sequence_i5, i.index_kit_i7_id) for i in library.indices] == [(rc_i7, rc_i5, kit.id)]
    assert library.indices[0].orientation == C.BarcodeOrientation.FORWARD


def test_reindex_i7_kit_with_custom_i5(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str,
):
    """Regression: a kit i7 (validated) with a custom i5 (not validated) failed with 'Conflicting orientations'."""
    kit = _kit(session, C.IndexType.DUAL_INDEX, [[(C.BarcodeType.INDEX_I7, I7), (C.BarcodeType.INDEX_I5, "TTTTCCCCGG")]])
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()

    params = _reindex_to_barcode_match(client, user_token, seq_request, library, sequence_i5=I5)
    _complete(client, user_token, params, {
        "i7_kit": str(kit.id), "i5_kit": "0", "i5_option": "forward", "i5_primer": PRIMER,
    })

    session.expire_all()
    library = session.get_one(Q.library.select(id=library.id))
    assert [(i.name_i7, i.index_kit_i7_id, i.sequence_i5, i.index_kit_i5_id) for i in library.indices] == [
        ("KIT_INDEX_I7_0", kit.id, I5, None),
    ]
    assert library.indices[0].orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED


def test_reindex_i7_kit_with_unknown_i5_orientation_is_not_validated(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token: str,
):
    """The index is validated only if both i7 and i5 are; an unknown i5 needs a manual check."""
    kit = _kit(session, C.IndexType.DUAL_INDEX, [[(C.BarcodeType.INDEX_I7, I7), (C.BarcodeType.INDEX_I5, "TTTTCCCCGG")]])
    seq_request = create_seq_request(session, user)
    library = create_library(session, user, seq_request)
    session.commit()

    params = _reindex_to_barcode_match(client, user_token, seq_request, library, sequence_i5=I5)
    _complete(client, user_token, params, {
        "i7_kit": str(kit.id), "i5_kit": "0", "i5_option": "idk", "i5_primer": PRIMER,
    })

    session.expire_all()
    library = session.get_one(Q.library.select(id=library.id))
    assert library.indices[0].orientation == C.BarcodeOrientation.FORWARD_NOT_VALIDATED
