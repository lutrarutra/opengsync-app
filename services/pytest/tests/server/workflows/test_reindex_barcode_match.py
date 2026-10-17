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
