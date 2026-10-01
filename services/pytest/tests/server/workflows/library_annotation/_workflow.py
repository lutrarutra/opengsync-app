"""Shared driver for LibraryAnnotationWorkflow HTTP tests."""

import ast
import re
import uuid
from typing import Any

from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ..._http import get, post_form, spreadsheet_payload, OpenGSyncTestClient

HUMAN = C.GenomeRef.HUMAN.display_name
MOUSE = C.GenomeRef.MOUSE.display_name


class AnnotationWorkflow:
    """Drives one library-annotation workflow run for a sequencing request."""

    def __init__(self, client: OpenGSyncTestClient, token: str, seq_request_id: int) -> None:
        self.client = client
        self.token = token
        self.seq_request_id = seq_request_id
        self.uuid = str(uuid.uuid4())
        self.params = {"uuid": self.uuid}
        self.prefix = f"/htmx/workflows/library-annotation/{seq_request_id}"

    def begin(self):
        response = get(self.client, f"{self.prefix}/begin", self.token, params=self.params)
        assert response.status_code == 200, response.text
        return response

    def post(self, step: str, data: dict[str, Any] | None = None, status: int = 200, next_step: str | None = None):
        """POST a step and, when ``next_step`` is given, assert the rendered step is that one."""
        response = post_form(
            self.client, f"{self.prefix}/{step}", data or {},
            token=self.token, params=self.params,
        )
        assert response.status_code == status, f"{step}: expected status {status}, got {response.status_code}"
        if next_step is not None:
            assert self.rendered_step(response) == next_step, f"{step}: expected next step '{next_step}', got '{self.rendered_step(response)}'"
        return response

    def rendered_step(self, response) -> str | None:
        """Slug of the step the response posts to (i.e. the step that was rendered)."""
        # Forms post via hx-post, spreadsheets via htmx.ajax("POST", ...); "Previous" links are GETs.
        path = rf"(?:https?://[^/\"]+)?{re.escape(self.prefix)}/([a-z0-9-]+)\?uuid"
        steps = re.findall(rf'hx-post="{path}', response.text) + re.findall(rf'htmx\.ajax\("POST", "{path}', response.text)
        return steps[0] if steps else None

    def back(self, step: str, status: int = 200):
        """GET a step's 'Previous' route, i.e. what the 'Back' button of the following step does."""
        response = get(self.client, f"{self.prefix}/{step}", self.token, params=self.params)
        assert response.status_code == status, f"back to {step}: expected status {status}, got {response.status_code}"
        assert self.rendered_step(response) == step
        return response

    def back_step(self, response) -> str | None:
        """Slug of the step the rendered 'Back' button returns to."""
        steps = re.findall(rf'hx-get="(?:https?://[^/\"]+)?{re.escape(self.prefix)}/([a-z0-9-]+)\?uuid', response.text)
        return steps[-1] if steps else None

    def project(self, title: str, description: str = "test project", next_step: str = "sample-annotation"):
        return self.post("project-select", {
            "new_project": title,
            "project_description": description,
        }, next_step=next_step)

    def samples(self, rows: list[list[str]], next_step: str = "sample-attribute-annotation"):
        """``rows`` are ``[sample_name, genome]`` pairs."""
        return self.post("sample-annotation", spreadsheet_payload(["Sample Name", "Genome"], rows), next_step=next_step)

    def attributes(self, sample_names: list[str], next_step: str = "select-service"):
        return self.post("sample-attribute-annotation", spreadsheet_payload(
            ["Sample Name", "Sample ID"],
            [[name, "(new)"] for name in sample_names],
        ), next_step=next_step)

    def service(self, service_type: C.ServiceType, next_step: str | None = None, status: int = 200, **flags: Any):
        """Submit select-service. ``flags`` are field names like ``optional_assays-vdj_b='on'``."""
        data: dict[str, Any] = {"service_type": str(service_type.id)}
        data.update({k.replace("__", "-"): v for k, v in flags.items()})
        return self.post("select-service", data, status=status, next_step=next_step)

    def complete(self):
        response = self.post("complete-s-a-s", status=204)
        assert "HX-Redirect" in response.headers
        return response

    def assert_cleaned_up(self) -> None:
        leftover = Redis(connection_pool=self.client.app.state.redis_pool).keys(
            f"LibraryAnnotationWorkflow:{self.uuid}:*"
        )
        assert leftover == []


def libraries_by_name(session: SyncSession, seq_request_id: int) -> dict[str, models.Library]:
    session.expire_all()
    return {
        library.name: library
        for library in session.get_all(Q.library.select(seq_request_id=seq_request_id), limit=None)
    }


def linked_samples(library: models.Library) -> dict[str, dict | None]:
    """Map of sample name -> mux dict for every sample linked to ``library``."""
    return {link.sample.name: link.mux for link in library.sample_links}


def spreadsheet_rows(response) -> list[list]:
    """Rows the server pre-filled into the rendered spreadsheet."""
    match = re.search(r"data: (\[\[.*?\]\]),\n", response.text)
    assert match is not None, "no spreadsheet data in response"
    return ast.literal_eval(match.group(1))


def spreadsheet(columns: list[str], rows: list[list[Any]]) -> dict[str, str]:
    return spreadsheet_payload(columns, rows)


ABC_LIBRARY_TYPES = (C.LibraryType.TENX_ANTIBODY_CAPTURE, C.LibraryType.TENX_SC_ABC_FLEX)


def assert_features_only_on_abc_libraries(libraries: dict[str, models.Library]) -> None:
    """Antibody features (also rows without 'Sample Name') are linked to antibody-capture libraries only."""
    wrongly_linked = sorted(
        name for name, library in libraries.items()
        if library.type not in ABC_LIBRARY_TYPES and library.features
    )
    assert wrongly_linked == [], f"features linked to non-antibody-capture libraries: {wrongly_linked}"


def create_dual_index_kit(
    session: SyncSession, identifier: str, name: str,
    wells: dict[str, tuple[str, str, str, str]],
) -> models.IndexKit:
    """Dual-index kit; ``wells`` maps well -> (name_i7, sequence_i7, name_i5, sequence_i5)."""
    kit = session.save(Q.index_kit.create(
        name=name, identifier=identifier, type=C.IndexType.DUAL_INDEX, supported_protocol_ids=[],
    ), flush=True)
    for well, (name_i7, seq_i7, name_i5, seq_i5) in wells.items():
        adapter = session.save(Q.adapter.create(index_kit=kit, well=well), flush=True)
        session.save(Q.barcode.create(name=name_i7, sequence=seq_i7, well=well, type=C.BarcodeType.INDEX_I7, adapter=adapter), flush=True)
        session.save(Q.barcode.create(name=name_i5, sequence=seq_i5, well=well, type=C.BarcodeType.INDEX_I5, adapter=adapter), flush=True)
    session.commit()
    return kit


BARCODE_COLUMNS = [
    "Library Name", "Index Well", "i7 Kit", "i7 Name", "i7 Sequence",
    "i5 Kit", "i5 Name", "i5 Sequence",
]


def pool_mapping(pools: list[str]) -> dict[str, str]:
    data = {
        "contact_name": "Test Contact",
        "contact_email": "contact@example.com",
        "contact_phone": "123456",
    }
    for i, pool in enumerate(pools):
        data[f"pool_forms-{i}-raw_label"] = pool
        data[f"pool_forms-{i}-new_pool_name"] = pool
    return data


def create_tenx_atac_index_kit(
    session: SyncSession, identifier: str, name: str,
    wells: dict[str, tuple[str, list[str]]],
) -> models.IndexKit:
    """10X ATAC kit; ``wells`` maps well -> (name, [sequence_1, .., sequence_4])."""
    kit = session.save(Q.index_kit.create(
        name=name, identifier=identifier, type=C.IndexType.TENX_ATAC_INDEX, supported_protocol_ids=[],
    ), flush=True)
    for well, (barcode_name, sequences) in wells.items():
        adapter = session.save(Q.adapter.create(index_kit=kit, well=well), flush=True)
        for sequence in sequences:
            session.save(Q.barcode.create(name=barcode_name, sequence=sequence, well=well, type=C.BarcodeType.INDEX_I7, adapter=adapter), flush=True)
    session.commit()
    return kit


ATAC_BARCODE_COLUMNS = [
    "Library Name", "Index Well", "Kit", "Barcode Name",
    "Sequence 1", "Sequence 2", "Sequence 3", "Sequence 4",
]
