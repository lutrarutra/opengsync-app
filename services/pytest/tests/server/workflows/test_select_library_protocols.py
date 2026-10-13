"""SelectLibraryProtocolsWorkflow: set the protocol of every library in a lab prep.

As legacy ``select_library_protocols_workflow``: insider-only. Begin opens the protocol
spreadsheet (one row per library, prefilled with its current protocol) unless the lab prep's
prep file (``prep_table`` sheet) has a ``library_kits`` column. Then a mapping step comes
first: one row per kit combination (kit identifiers sorted, ``#`` prefix stripped), offering
the protocols whose kit links match it exactly (all protocols if none match). The chosen
protocols prefill the spreadsheet; submitting it saves each library's protocol (an empty
cell clears it) and redirects to the lab prep checklist.
"""

import os
import re
import uuid
from html import unescape
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C

from server.core import config

from ...db.create_units import create_lab_prep, create_library, create_protocol, create_seq_request
from .._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    post_form,
    post_form_csrf_mismatch,
    spreadsheet_payload,
)
from .library_annotation._workflow import spreadsheet_rows

COLUMNS = ["Library", "Protocol"]
MULTIPLE = "Multiple protocols found for this kit combination"
UNKNOWN = -1


def _url(client: TestClient, route: str) -> str:
    return client.app.url_path_for(f"SelectLibraryProtocolsWorkflow.{route}")  # type: ignore[attr-defined]


@pytest.fixture
def media_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config.settings.app_config, "media_folder", str(tmp_path))
    return tmp_path


class Setup:
    """An insider's lab prep with libraries l1, l2, l3 and kits ka, kb, kc.

    Protocols: ``p_ab`` links ka + kb (one combination), ``p_c1`` and ``p_c2`` both link kc,
    ``p_other`` links no kit.
    """

    def __init__(self, session: SyncSession, user: models.User, insider: models.User, media_folder: Path):
        self.session = session
        self.media_folder = media_folder
        self.lab_prep = create_lab_prep(session, insider)
        seq_request = create_seq_request(session, user)
        self.l1, self.l2, self.l3 = (self._library(user, seq_request) for _ in range(3))

        suffix = uuid.uuid4().hex[:6]
        self.ka, self.kb, self.kc = (
            session.save(Q.kit.create(name=f"Kit {k} {suffix}", identifier=f"K{k}{suffix}", kit_type=C.KitType.LIBRARY_KIT), flush=True)
            for k in "ABC"
        )
        self.p_ab = self._protocol("AB", [self.ka, self.kb])
        self.p_c1 = self._protocol("C1", [self.kc])
        self.p_c2 = self._protocol("C2", [self.kc])
        self.p_other = self._protocol("Other", [])
        session.commit()

    @property
    def ab(self) -> str:
        """The normalised kit combination of ka + kb."""
        return ";".join(sorted([self.ka.identifier, self.kb.identifier]))

    def _library(self, user: models.User, seq_request: models.SeqRequest) -> models.Library:
        library = create_library(self.session, user, seq_request)
        library.lab_prep_id = self.lab_prep.id
        return self.session.save(library, flush=True)

    def _protocol(self, name: str, kits: list[models.Kit]) -> models.Protocol:
        protocol = create_protocol(self.session)
        protocol.name = f"Protocol {name} {protocol.name[:8]}"
        for kit in kits:
            protocol.kit_links.append(models.links.ProtocolKitLink(protocol_id=protocol.id, kit_id=kit.id, combination_num=1))
        return self.session.save(protocol, flush=True)

    def prep_file(self, rows: list[dict] | None, on_disk: bool = True) -> None:
        media_file = self.session.save(Q.media_file.create(
            name="prep", type=C.MediaFileType.LIBRARY_PREP_FILE, extension=".xlsx",
            uploader_id=self.lab_prep.creator_id, size_bytes=1, uuid=str(uuid.uuid4()), lab_prep_id=self.lab_prep.id,
        ), flush=True)
        if on_disk:
            path = self.media_folder / media_file.path
            os.makedirs(path.parent, exist_ok=True)
            pd.DataFrame(rows).to_excel(path, sheet_name="prep_table", index=False)
        self.session.commit()

    def kits_file(self) -> None:
        """l1: ka + kb (unsorted, with '#' and spaces); l2: kc; l3: no kits."""
        self.prep_file([
            {"library_id": self.l1.id, "library_name": self.l1.name, "library_kits": f" #{self.kb.identifier}; {self.ka.identifier}"},
            {"library_id": self.l2.id, "library_name": self.l2.name, "library_kits": self.kc.identifier},
            {"library_id": self.l3.id, "library_name": self.l3.name, "library_kits": None},
        ])

    def set_protocol(self, library: models.Library, protocol: models.Protocol | None) -> None:
        library.protocol_id = protocol.id if protocol else None
        self.session.save(library, flush=True)
        self.session.commit()

    def protocols(self) -> dict[int, int | None]:
        self.session.expire_all()
        return {
            library.id: self.session.get_one(Q.library.select(id=library.id)).protocol_id
            for library in (self.l1, self.l2, self.l3)
        }


@pytest.fixture
def setup(session: SyncSession, user, insider, media_folder: Path) -> Setup:
    return Setup(session, user, insider, media_folder)


def _begin(client: TestClient, setup: Setup, token: str):
    return get(client, _url(client, "Begin"), token, params={"lab_prep_id": setup.lab_prep.id})


def _params(setup: Setup, response) -> dict:
    match = re.search(r"uuid=([0-9a-f-]{36})", unescape(response.text))
    assert match, "workflow uuid not found in response"
    return {"lab_prep_id": setup.lab_prep.id, "uuid": match.group(1)}


def _mapping(response) -> dict[str, tuple[str | None, list[str], bool]]:
    """Per mapping row: kit combination -> (selected protocol id, option ids, has 'multiple' error)."""
    html = unescape(response.text)
    rows = {}
    for i, combination in re.findall(r'id="subforms-(\d+)-kit_combination" value="([^"]*)"', html):
        block = re.search(rf'name="subforms-{i}-protocol".*?(?=subforms-{int(i) + 1}-kit_combination|$)', html, re.S)
        assert block, f"protocol select {i} not found"
        select, _, feedback = block.group(0).partition("</select>")
        options = re.findall(r'<option value="([^"]*)"', select)
        selected = re.search(r'<option value="([^"]*)"\s+selected', select)
        rows[combination] = (selected.group(1) if selected else None, options, MULTIPLE in feedback)
    return rows


def _mapping_payload(selection: dict[str, int]) -> dict[str, str]:
    payload = {}
    for i, (combination, protocol_id) in enumerate(sorted(selection.items())):
        payload[f"subforms-{i}-kit_combination"] = combination
        payload[f"subforms-{i}-protocol"] = str(protocol_id)
    return payload


def _table(response) -> dict[str, str]:
    """Spreadsheet rows as library name -> protocol name ('' if none)."""
    return {row[0]: row[1] or "" for row in spreadsheet_rows(response)}


def _submit_table(client: TestClient, setup: Setup, token: str, params: dict, rows: list[tuple[models.Library, models.Protocol | None]]):
    payload = spreadsheet_payload(COLUMNS, [[library.name, protocol.name if protocol else ""] for library, protocol in rows])
    return post_form(client, _url(client, "LibraryProtocolSelectForm.Submit"), payload, token=token, params=params)


# ── Begin: which step comes first ───────────────────────────────────────────


def test_without_prep_file_opens_spreadsheet_prefilled_with_current_protocols(
    client: TestClient, setup: Setup, insider_token: str,
):
    setup.set_protocol(setup.l1, setup.p_other)

    response = _begin(client, setup, insider_token)

    assert response.status_code == 200, response.text
    assert "subforms-0-protocol" not in response.text
    assert _table(response) == {setup.l1.name: setup.p_other.name, setup.l2.name: "", setup.l3.name: ""}


def test_prep_file_without_library_kits_skips_mapping(client: TestClient, setup: Setup, insider_token: str):
    setup.prep_file([{"library_id": setup.l1.id, "library_name": setup.l1.name}])

    response = _begin(client, setup, insider_token)

    assert response.status_code == 200, response.text
    assert "subforms-0-protocol" not in response.text
    assert set(_table(response)) == {setup.l1.name, setup.l2.name, setup.l3.name}


def test_prep_file_with_empty_library_kits_skips_mapping(client: TestClient, setup: Setup, insider_token: str):
    setup.prep_file([{"library_id": setup.l1.id, "library_name": setup.l1.name, "library_kits": None}])

    response = _begin(client, setup, insider_token)

    assert response.status_code == 200, response.text
    assert "subforms-0-protocol" not in response.text
    assert set(_table(response)) == {setup.l1.name, setup.l2.name, setup.l3.name}


def test_missing_prep_file_on_disk_warns_and_skips_mapping(client: TestClient, setup: Setup, insider_token: str):
    setup.prep_file(None, on_disk=False)

    response = _begin(client, setup, insider_token)

    assert response.status_code == 200, response.text
    assert_flash(response, "Library prep file not found..", "warning")
    assert set(_table(response)) == {setup.l1.name, setup.l2.name, setup.l3.name}


# ── Mapping step ────────────────────────────────────────────────────────────


def test_library_kits_open_mapping_with_one_row_per_normalised_combination(
    client: TestClient, setup: Setup, insider_token: str,
):
    setup.kits_file()

    response = _begin(client, setup, insider_token)

    assert response.status_code == 200, response.text
    assert set(_mapping(response)) == {setup.ab, setup.kc.identifier}


def test_unique_matching_protocol_is_preselected(client: TestClient, setup: Setup, insider_token: str):
    setup.kits_file()

    selected, options, multiple = _mapping(_begin(client, setup, insider_token))[setup.ab]

    assert options == [str(UNKNOWN), str(setup.p_ab.id)]
    assert selected == str(setup.p_ab.id)
    assert not multiple


def test_several_matching_protocols_are_offered_with_a_warning(client: TestClient, setup: Setup, insider_token: str):
    setup.kits_file()

    selected, options, multiple = _mapping(_begin(client, setup, insider_token))[setup.kc.identifier]

    assert set(options) == {str(UNKNOWN), str(setup.p_c1.id), str(setup.p_c2.id)}
    assert selected == options[-1]
    assert multiple


def test_combination_without_matching_protocol_offers_all_protocols_and_selects_unknown(
    client: TestClient, session: SyncSession, setup: Setup, insider_token: str,
):
    """As legacy: every protocol is offered, 'Unknown' stays selected and there is no 'multiple' warning."""
    setup.prep_file([{"library_id": setup.l1.id, "library_name": setup.l1.name, "library_kits": setup.ka.identifier}])

    selected, options, multiple = _mapping(_begin(client, setup, insider_token))[setup.ka.identifier]

    assert options[0] == str(UNKNOWN)
    assert {str(p.id) for p in (setup.p_ab, setup.p_c1, setup.p_c2, setup.p_other)} <= set(options)
    assert selected == str(UNKNOWN)
    assert not multiple


def test_combination_without_match_preselects_the_libraries_current_protocol(
    client: TestClient, setup: Setup, insider_token: str,
):
    setup.set_protocol(setup.l1, setup.p_other)
    setup.prep_file([{"library_id": setup.l1.id, "library_name": setup.l1.name, "library_kits": setup.ka.identifier}])

    selected, _, multiple = _mapping(_begin(client, setup, insider_token))[setup.ka.identifier]

    assert selected == str(setup.p_other.id)
    assert not multiple


def test_current_protocol_outside_the_matches_is_added_and_preselected(
    client: TestClient, setup: Setup, insider_token: str,
):
    """As legacy: it is appended to the matching protocols, which then count as 'multiple'."""
    setup.set_protocol(setup.l1, setup.p_other)
    setup.kits_file()

    selected, options, multiple = _mapping(_begin(client, setup, insider_token))[setup.ab]

    assert options == [str(UNKNOWN), str(setup.p_ab.id), str(setup.p_other.id)]
    assert selected == str(setup.p_other.id)
    assert multiple


def test_mapping_prefills_spreadsheet_and_unknown_keeps_current_protocol(
    client: TestClient, setup: Setup, insider_token: str,
):
    setup.set_protocol(setup.l3, setup.p_other)
    setup.kits_file()
    params = _params(setup, _begin(client, setup, insider_token))

    response = post_form(
        client, _url(client, "ProtocolMappingForm.Submit"),
        _mapping_payload({setup.ab: setup.p_ab.id, setup.kc.identifier: UNKNOWN}), token=insider_token, params=params,
    )

    assert response.status_code == 200, response.text
    assert _table(response) == {setup.l1.name: setup.p_ab.name, setup.l2.name: "", setup.l3.name: setup.p_other.name}
    assert setup.protocols() == {setup.l1.id: None, setup.l2.id: None, setup.l3.id: setup.p_other.id}  # nothing saved yet


def test_previous_returns_to_mapping_with_the_chosen_protocols(client: TestClient, setup: Setup, insider_token: str):
    setup.kits_file()
    params = _params(setup, _begin(client, setup, insider_token))
    post_form(
        client, _url(client, "ProtocolMappingForm.Submit"),
        _mapping_payload({setup.ab: setup.p_ab.id, setup.kc.identifier: setup.p_c1.id}), token=insider_token, params=params,
    )

    response = get(client, _url(client, "ProtocolMappingForm.Previous"), insider_token, params=params)

    assert response.status_code == 200, response.text
    mapping = _mapping(response)
    assert mapping[setup.ab][0] == str(setup.p_ab.id)
    assert mapping[setup.kc.identifier][0] == str(setup.p_c1.id)


def test_spreadsheet_after_mapping_links_back_to_mapping(client: TestClient, setup: Setup, insider_token: str):
    setup.kits_file()
    params = _params(setup, _begin(client, setup, insider_token))

    response = post_form(
        client, _url(client, "ProtocolMappingForm.Submit"),
        _mapping_payload({setup.ab: setup.p_ab.id, setup.kc.identifier: setup.p_c1.id}), token=insider_token, params=params,
    )

    assert _url(client, "ProtocolMappingForm.Previous") in unescape(response.text)


def test_prep_file_with_one_row_per_index_repeats_libraries(client: TestClient, setup: Setup, insider_token: str):
    """As legacy: the spreadsheet has one row per prep-table row, so a library with several index rows repeats."""
    rows = []
    for library, kits in ((setup.l1, setup.ab), (setup.l2, setup.kc.identifier)):
        for well in ("A1", "A2"):
            rows.append({"library_id": library.id, "library_name": library.name, "index_well": well, "library_kits": kits})
    setup.prep_file(rows)
    params = _params(setup, _begin(client, setup, insider_token))

    response = post_form(
        client, _url(client, "ProtocolMappingForm.Submit"),
        _mapping_payload({setup.ab: setup.p_ab.id, setup.kc.identifier: setup.p_c2.id}), token=insider_token, params=params,
    )

    assert response.status_code == 200, response.text
    assert [(row[0], row[1]) for row in spreadsheet_rows(response)] == [
        (setup.l1.name, setup.p_ab.name), (setup.l1.name, setup.p_ab.name),
        (setup.l2.name, setup.p_c2.name), (setup.l2.name, setup.p_c2.name),
    ]

    response = _submit_table(client, setup, insider_token, params, [
        (setup.l1, setup.p_ab), (setup.l1, setup.p_ab), (setup.l2, setup.p_c2), (setup.l2, setup.p_c2),
    ])

    assert_htmx_redirect(response, f"/lab_preps/{setup.lab_prep.id}")
    assert setup.protocols() == {setup.l1.id: setup.p_ab.id, setup.l2.id: setup.p_c2.id, setup.l3.id: None}


# ── Completion ──────────────────────────────────────────────────────────────


def test_full_flow_saves_protocols_and_clears_state(client: TestClient, setup: Setup, insider_token: str):
    setup.kits_file()
    params = _params(setup, _begin(client, setup, insider_token))
    post_form(
        client, _url(client, "ProtocolMappingForm.Submit"),
        _mapping_payload({setup.ab: setup.p_ab.id, setup.kc.identifier: setup.p_c2.id}), token=insider_token, params=params,
    )

    response = _submit_table(client, setup, insider_token, params, [
        (setup.l1, setup.p_ab), (setup.l2, setup.p_c2), (setup.l3, setup.p_other),
    ])

    assert_htmx_redirect(response, f"/lab_preps/{setup.lab_prep.id}")
    assert "lab_prep-checklist-tab" in response.headers["HX-Redirect"]
    assert_flash(response, "Protocols Submitted!", "success")
    assert setup.protocols() == {setup.l1.id: setup.p_ab.id, setup.l2.id: setup.p_c2.id, setup.l3.id: setup.p_other.id}
    leftover = Redis(connection_pool=client.app.state.redis_pool).keys(f"*{params['uuid']}*")  # type: ignore[attr-defined]
    assert leftover == []


def test_empty_protocol_cell_clears_the_protocol(client: TestClient, setup: Setup, insider_token: str):
    setup.set_protocol(setup.l1, setup.p_other)
    setup.set_protocol(setup.l2, setup.p_other)
    params = _params(setup, _begin(client, setup, insider_token))

    response = _submit_table(client, setup, insider_token, params, [(setup.l1, None), (setup.l2, setup.p_c1), (setup.l3, None)])

    assert_htmx_redirect(response, f"/lab_preps/{setup.lab_prep.id}")
    assert setup.protocols() == {setup.l1.id: None, setup.l2.id: setup.p_c1.id, setup.l3.id: None}


def test_rows_left_out_keep_their_protocol(client: TestClient, setup: Setup, insider_token: str):
    setup.set_protocol(setup.l3, setup.p_other)
    params = _params(setup, _begin(client, setup, insider_token))

    response = _submit_table(client, setup, insider_token, params, [(setup.l1, setup.p_c1)])

    assert_htmx_redirect(response, f"/lab_preps/{setup.lab_prep.id}")
    assert setup.protocols() == {setup.l1.id: setup.p_c1.id, setup.l2.id: None, setup.l3.id: setup.p_other.id}


def test_unknown_protocol_is_rejected(client: TestClient, setup: Setup, insider_token: str):
    params = _params(setup, _begin(client, setup, insider_token))
    payload = spreadsheet_payload(COLUMNS, [[setup.l1.name, "No such protocol"]])

    response = post_form(client, _url(client, "LibraryProtocolSelectForm.Submit"), payload, token=insider_token, params=params)

    assert_form_invalid(response)
    assert setup.protocols()[setup.l1.id] is None


def test_library_outside_the_lab_prep_is_rejected(
    client: TestClient, session: SyncSession, setup: Setup, user, insider_token: str,
):
    outsider = create_library(session, user, create_seq_request(session, user))
    session.commit()
    params = _params(setup, _begin(client, setup, insider_token))

    response = _submit_table(client, setup, insider_token, params, [(outsider, setup.p_c1)])

    assert_form_invalid(response)
    session.expire_all()
    assert session.get_one(Q.library.select(id=outsider.id)).protocol_id is None


# ── Access ──────────────────────────────────────────────────────────────────


def test_client_is_denied(client: TestClient, setup: Setup, user_token: str):
    setup.kits_file()
    params = {"lab_prep_id": setup.lab_prep.id, "uuid": str(uuid.uuid4())}

    assert _begin(client, setup, user_token).status_code == 403
    assert post_form(
        client, _url(client, "ProtocolMappingForm.Submit"), _mapping_payload({setup.ab: setup.p_ab.id}), token=user_token, params=params,
    ).status_code == 403
    assert _submit_table(client, setup, user_token, params, [(setup.l1, setup.p_c1)]).status_code == 403
    assert setup.protocols()[setup.l1.id] is None


def test_unknown_lab_prep_is_404(client: TestClient, insider_token: str):
    assert get(client, _url(client, "Begin"), insider_token, params={"lab_prep_id": 999999}).status_code == 404


def test_anonymous_is_redirected_to_login(client: TestClient, setup: Setup):
    assert _begin(client, setup, None).status_code == 303


def test_csrf_mismatch_changes_nothing(client: TestClient, setup: Setup, insider_token: str):
    params = _params(setup, _begin(client, setup, insider_token))
    payload = spreadsheet_payload(COLUMNS, [[setup.l1.name, setup.p_c1.name]])

    response = post_form_csrf_mismatch(client, _url(client, "LibraryProtocolSelectForm.Submit"), payload, token=insider_token, params=params)

    assert response.status_code != 200 or "HX-Redirect" not in response.headers
    assert setup.protocols()[setup.l1.id] is None
