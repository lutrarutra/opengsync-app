"""LibraryAnnotationWorkflow: pooled-libraries bulk RNA-seq happy path and validation."""

import uuid
from typing import Any

from redis import Redis

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ....db.create_units import create_seq_request
from ..._http import get, post_form, spreadsheet_payload, OpenGSyncTestClient


def test_simple_pooled_bulk_rna_seq_annotation(
    client: OpenGSyncTestClient, session: SyncSession, user, user_token,
):
    session.save(Q.pool.create(
        name="Taken_Pool",
        owner_id=user.id,
        contact_name="n",
        contact_email="n@e.com",
        pool_type=C.PoolType.EXTERNAL,
        clone_number=0,
        seq_request_id=None,
    ), flush=True)
    session.commit()

    seq_request = create_seq_request(session, user, submission_type=C.SubmissionType.POOLED_LIBRARIES)
    session.commit()
    wf_uuid = str(uuid.uuid4())
    params = {"uuid": wf_uuid}
    prefix = f"/htmx/workflows/library-annotation/{seq_request.id}"

    def post(step: str, data: dict[str, Any] | None = None, status: int = 200):
        response = post_form(
            client, f"{prefix}/{step}", data or {},
            token=user_token, params=params,
        )
        assert response.status_code == status
        return response

    begun = get(client, f"{prefix}/begin", user_token, params=params)
    assert begun.status_code == 200

    project_title = "BULK RNA-seq Project from pooled libraries test"
    post("project-select", {
        "new_project": project_title,
        "project_description": "test project for pooled library submission, simple",
    })

    human = C.GenomeRef.HUMAN.display_name
    post("sample-annotation", spreadsheet_payload(["Sample Name", "Genome"], [
        ["Sample_A", human],
        ["Sample_B", human],
    ]))
    post("sample-attribute-annotation", spreadsheet_payload(
        ["Sample Name", "Sample ID", "Test Attribute"],
        [
            ["Sample_A", "(new)", "Test Attribute A"],
            ["Sample_B", "(new)", "Test Attribute B"],
        ],
    ))
    post("select-service", {"service_type": str(C.ServiceType.BULK_RNA_SEQ.id)})

    lib_a = f"Sample_A_{C.LibraryType.BULK_RNA_SEQ.identifier}"
    lib_b = f"Sample_B_{C.LibraryType.BULK_RNA_SEQ.identifier}"
    pool_columns = ["Library Name", "Pool"]
    pool_name_max = models.Pool.name.type.length

    post("pooled-library-annotation", spreadsheet_payload(pool_columns, []), status=202)  # empty spreadsheet
    post("pooled-library-annotation", {
        "spreadsheet": "not-json",
        "columns": '["Library Name", "Pool"]',
    }, status=202)  # invalid spreadsheet JSON
    post("pooled-library-annotation", spreadsheet_payload(["Library Name"], [
        [lib_a],
        [lib_b],
    ]), status=202)  # missing Pool column
    post("pooled-library-annotation", spreadsheet_payload(["Pool"], [
        ["Pool_A"],
        ["Pool_B"],
    ]), status=202)  # missing Library Name column
    post("pooled-library-annotation", spreadsheet_payload(pool_columns, [
        ["", "Pool_A"],
        [lib_b, "Pool_B"],
    ]), status=202)  # empty library name
    post("pooled-library-annotation", spreadsheet_payload(pool_columns, [
        [lib_a, ""],
        [lib_b, "Pool_B"],
    ]), status=202)  # empty pool name
    post("pooled-library-annotation", spreadsheet_payload(pool_columns, [
        [lib_a, "   "],
        [lib_b, "Pool_B"],
    ]), status=202)  # whitespace-only pool name
    post("pooled-library-annotation", spreadsheet_payload(pool_columns, [
        [lib_a, "abc"],
        [lib_b, "Pool_B"],
    ]), status=202)  # pool name shorter than 4 characters
    post("pooled-library-annotation", spreadsheet_payload(pool_columns, [
        [lib_a, "P" * (pool_name_max + 1)],
        [lib_b, "Pool_B"],
    ]), status=202)  # pool name longer than max length

    post("pooled-library-annotation", spreadsheet_payload(pool_columns, [
        [lib_a, "Pool_A"],
        [lib_b, "Pool_B"],
    ]))

    def mapping(**overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "contact_name": "Test Contact",
            "contact_email": "contact@example.com",
            "contact_phone": "123456",
            "pool_forms-0-raw_label": "Pool_A",
            "pool_forms-0-new_pool_name": "Pool_A",
            "pool_forms-1-raw_label": "Pool_B",
            "pool_forms-1-new_pool_name": "Pool_B",
        }
        data.update(overrides)
        return data

    post("pool-mapping", mapping(contact_name=""), status=202)  # contact name is required
    post("pool-mapping", mapping(contact_email=""), status=202)  # contact email is required
    post("pool-mapping", mapping(contact_phone=""), status=202)  # contact phone is required
    post("pool-mapping", mapping(contact_name="N" * (models.Contact.name.type.length + 1)), status=202)  # contact name longer than max length
    post("pool-mapping", mapping(contact_email="E" * (models.Contact.email.type.length + 1)), status=202)  # contact email longer than max length
    post("pool-mapping", mapping(contact_phone="1" * (models.Contact.phone.type.length + 1)), status=202)  # contact phone longer than max length
    post("pool-mapping", mapping(**{"pool_forms-0-raw_label": ""}), status=202)  # raw pool label is required
    post("pool-mapping", mapping(**{"pool_forms-0-new_pool_name": ""}), status=202)  # pool name is required
    post("pool-mapping", mapping(**{"pool_forms-0-new_pool_name": "ab"}), status=202)  # pool name shorter than 3 characters
    post("pool-mapping", mapping(**{"pool_forms-0-new_pool_name": "P" * (pool_name_max + 1)}), status=202)  # pool name longer than max length
    post("pool-mapping", mapping(**{"pool_forms-0-new_pool_name": "Pool A"}), status=202)  # space is not allowed in pool names
    post("pool-mapping", mapping(**{"pool_forms-0-new_pool_name": "Pool@A"}), status=202)  # '@' is not allowed in pool names
    post("pool-mapping", mapping(**{
        "pool_forms-0-new_pool_name": "Same_Pool",
        "pool_forms-1-new_pool_name": "Same_Pool",
    }), status=202)  # duplicate pool name within this submission
    post("pool-mapping", mapping(**{"pool_forms-0-new_pool_name": "Taken_Pool"}), status=202)  # owner already has a pool with this name
    post("pool-mapping", mapping(**{"pool_forms-0-num_m_reads_requested": "not-a-number"}), status=202)  # requested reads must be a number

    post("pool-mapping", mapping())

    barcode_columns = [
        "Library Name", "Index Well", "i7 Kit", "i7 Name", "i7 Sequence",
        "i5 Kit", "i5 Name", "i5 Sequence",
    ]
    seq_max = models.LibraryIndex.sequence_i7.type.length
    name_max = models.LibraryIndex.name_i7.type.length

    def barcode_row(
        library: str, well: str = "", kit_i7: str = "", name_i7: str = "", seq_i7: str = "",
        kit_i5: str = "", name_i5: str = "", seq_i5: str = "",
    ) -> list[str]:
        return [library, well, kit_i7, name_i7, seq_i7, kit_i5, name_i5, seq_i5]

    post("barcode-input", spreadsheet_payload(barcode_columns, []), status=202)  # empty spreadsheet
    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row("Unknown_Lib", seq_i7="ACGTACGT"),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]), status=202)  # library name is not one of the annotated libraries
    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row(lib_a),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]), status=202)  # missing i7 sequence
    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row(lib_a, well="A1"),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]), status=202)  # index well without kit or sequence
    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row(lib_a, seq_i7="A" * (seq_max + 1)),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]), status=202)  # i7 sequence longer than max length
    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row(lib_a, seq_i7="ACGTACGT", seq_i5="A" * (seq_max + 1)),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]), status=202)  # i5 sequence longer than max length
    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row(lib_a, well="A12345678", seq_i7="ACGTACGT"),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]), status=202)  # index well longer than 8 characters
    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row(lib_a, name_i7="N" * (name_max + 1), seq_i7="ACGTACGT"),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]), status=202)  # i7 name longer than max length
    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row(lib_a, name_i5="N" * (name_max + 1), seq_i7="ACGTACGT", seq_i5="TGCATGCA"),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]), status=202)  # i5 name longer than max length
    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row(lib_a, kit_i7="NOTAKIT", well="A1"),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]), status=202)  # i7 kit is not a known index kit
    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row(lib_a, kit_i5="NOTAKIT", seq_i7="ACGTACGT", seq_i5="TGCATGCA"),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]), status=202)  # i5 kit is not a known index kit

    post("barcode-input", spreadsheet_payload(barcode_columns, [
        barcode_row(lib_a, seq_i7="ACGTACGT"),
        barcode_row(lib_b, seq_i7="TGCATGCA"),
    ]))

    post("barcode-match", {}, status=202)  # i7 kit must be selected
    post("barcode-match", {"i7_kit": "0"}, status=202)  # custom i7 kit requires how to proceed
    post("barcode-match", {
        "i7_kit": "0",
        "i7_option": "forward",
    }, status=202)  # custom i7 kit requires a primer sequence
    post("barcode-match", {
        "i7_kit": "0",
        "i7_primer": "AATGATACGGCGACCACCGA",
    }, status=202)  # custom i7 kit requires how to proceed

    post("barcode-match", {
        "i7_kit": "0",
        "i7_option": "forward",
        "i7_primer": "AATGATACGGCGACCACCGA",
    })

    complete = post("complete-s-a-s", status=204)
    assert "HX-Redirect" in complete.headers

    session.expire_all()
    created_project = session.first(Q.project.select(title=project_title))
    assert created_project is not None

    samples_in_project = session.get_all(Q.sample.select(project_id=created_project.id), limit=None)
    assert len(samples_in_project) == 2
    assert samples_in_project[0].name == "Sample_A"
    assert samples_in_project[1].name == "Sample_B"

    libraries = session.get_all(Q.library.select(seq_request_id=seq_request.id), limit=None)
    assert len(libraries) == 2
    assert libraries[0].name == lib_a
    assert libraries[1].name == lib_b
    assert libraries[0].pool_id is not None
    assert libraries[1].pool_id is not None
    assert libraries[0].pool_id != libraries[1].pool_id
    assert libraries[0].pool.name == "Pool_A"
    assert libraries[1].pool.name == "Pool_B"
    assert len(libraries[0].indices) == 1
    assert len(libraries[1].indices) == 1
    assert libraries[0].indices[0].sequence_i7 == "ACGTACGT"
    assert libraries[1].indices[0].sequence_i7 == "TGCATGCA"
    assert libraries[0].index_type == C.IndexType.SINGLE_INDEX_I7
    assert libraries[1].index_type == C.IndexType.SINGLE_INDEX_I7

    pools = session.get_all(Q.pool.select(seq_request_id=seq_request.id), limit=None)
    assert len(pools) == 2
    assert {pool.name for pool in pools} == {"Pool_A", "Pool_B"}
    assert {pool.contact.name for pool in pools} == {"Test Contact"}

    leftover = Redis(connection_pool=client.app.state.redis_pool).keys(
        f"LibraryAnnotationWorkflow:{wf_uuid}:*"
    )
    assert leftover == []

    session.refresh(seq_request)
    assert seq_request.num_pools == 2
    assert seq_request.num_libraries == 2
