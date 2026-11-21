"""Seed the dev database with data for testing the htmx tables in a browser (search, filters, access rights).

Run inside the dev app container (make dev):

    docker exec -i opengsync-app-dev python - < scripts/dev_seed_tables.py

Creates, once (skipped when qa.insider@example.com exists), users that all log in with the password
``devpassword``:

    qa.admin@example.com       admin (the /admin tables)
    qa.insider@example.com     technician (insider, sees everything)
    qa.client@example.com      client, member of "QA Immunology Lab"
    qa.colleague@example.com   client, member of "QA Immunology Lab"
    qa.outsider@example.com    client, in no group: its request must never show up for qa.client

and per client a request, a project with samples, ~14 libraries with barcodes and a pool.
"""
import os
import sys

sys.path.insert(0, "/app/services/backend")

from opengsync_db import SyncDBHandler, queries as Q, models  # noqa: E402
from opengsync_db.categories import (  # noqa: E402
    UserRole, GroupType, AffiliationType, DataDeliveryMode, ReadType, SubmissionType, LibraryType, GenomeRef,
    ServiceType, LibraryStatus, PoolType, IndexType, ProjectStatus,
)
from server.core.secrets import BcryptCompat  # noqa: E402

PASSWORD = "devpassword"

LIBRARIES = [
    # name suffix, type, status, (i7 name, i7, i5)
    ("D01_GEX", LibraryType.TENX_SC_GEX_3PRIME, LibraryStatus.POOLED, ("SI-TT-A1", "GTAACATGCG", "AGTGTTACCT")),
    ("D01_ADT", LibraryType.TENX_ANTIBODY_CAPTURE, LibraryStatus.POOLED, ("SI-TN-A1", "CTAGCCTACG", "TTGACGGATC")),
    ("D02_GEX", LibraryType.TENX_SC_GEX_3PRIME, LibraryStatus.SEQUENCED, ("SI-TT-B4", "GTCAGGTTAC", "AATCGTCCGA")),
    ("D02_ADT", LibraryType.TENX_ANTIBODY_CAPTURE, LibraryStatus.SEQUENCED, ("SI-TN-B4", "AGGCTTAGCA", "CCATGACTTG")),
    ("D03_GEX", LibraryType.BULK_RNA_SEQ, LibraryStatus.ACCEPTED, ("UDI0046", "TCCGATAGGT", "GAGTCTCAAC")),
    ("D03_ATAC", LibraryType.TENX_SC_ATAC, LibraryStatus.PREPARING, ("N704+S502", "TCCTGAGC", "CTCTCTAT")),
    ("D04_GEX", LibraryType.BULK_RNA_SEQ, LibraryStatus.SHARED, ("SI-TT-C1", "ATCCGTGACA", "GGTAACTCGA")),
    ("D04_HTO", LibraryType.TENX_MUX_OLIGO, LibraryStatus.FAILED, ("SI-TN-A7", "GACTTGCAGA", "ACCTGTAGCT")),
    ("D05_GEX", LibraryType.BULK_RNA_SEQ, LibraryStatus.SUBMITTED, ("UDI0012", "GCAATTCGCA", "AGTCGGATTC")),
    ("D05_CRISPR", LibraryType.TENX_CRISPR_SCREENING, LibraryStatus.DRAFT, ("UDI0013", "CAGGTACCTT", "TGCAAGTTGC")),
    ("D06_GEX", LibraryType.BULK_RNA_SEQ, LibraryStatus.STORED, ("UDI0088", "ATGCGGTCAA", "GCTTACCAGT")),
    ("D06_WGS", LibraryType.BULK_RNA_SEQ, LibraryStatus.SEQUENCED, ("UDI0089", "TACCGAAGGT", "CGGTATGCAA")),
    ("D07_GEX", LibraryType.BULK_RNA_SEQ, LibraryStatus.POOLED, ("SI-TT-A7", "TTGGACCTAG", "CAGTACGTTC")),
    ("D07_ADT", LibraryType.TENX_ANTIBODY_CAPTURE, LibraryStatus.ACCEPTED, ("SI-TT-C2", "CGAATCGGTT", "TACGGAACTG")),
]


def main() -> None:
    db = SyncDBHandler(auto_commit=False, expire_on_commit=False)
    db.connect(
        user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"], port=os.environ.get("POSTGRES_PORT", 5432),
        db=os.environ.get("POSTGRES_DB", "opengsync_db"),
    )
    session = db.open_session()
    try:
        hashed = BcryptCompat(rounds=4).generate_password_hash(PASSWORD)
        if session.first(Q.user.select(email="qa.admin@example.com")) is None:
            session.save(Q.user.create(
                email="qa.admin@example.com", first_name="Ada", last_name="Admin", role=UserRole.ADMIN,
                hashed_password=hashed,
            ), flush=True)
            session.commit()
        if session.first(Q.user.select(email="qa.insider@example.com")) is not None:
            print("already seeded")
            return

        def user(email: str, first: str, last: str, role: UserRole) -> models.User:
            return session.save(Q.user.create(
                email=email, first_name=first, last_name=last, role=role, hashed_password=hashed,
            ), flush=True)

        user("qa.insider@example.com", "Ines", "Insider", UserRole.TECHNICIAN)
        client = user("qa.client@example.com", "Clara", "Client", UserRole.CLIENT)
        colleague = user("qa.colleague@example.com", "Colin", "Colleague", UserRole.CLIENT)
        outsider = user("qa.outsider@example.com", "Otto", "Outsider", UserRole.CLIENT)

        group = session.save(Q.group.create(name="QA Immunology Lab", type=GroupType.COLLABORATION), flush=True)
        session.save(Q.affiliation.create(user=client, group=group, type=AffiliationType.OWNER))
        session.save(Q.affiliation.create(user=colleague, group=group, type=AffiliationType.MEMBER))
        session.flush()

        for owner, title, request_name, in_group in [
            (client, "QA PBMC atlas", "QA PBMC atlas batch 3", True),
            (colleague, "QA Liver organoids", "QA Liver organoid time course", True),
            (outsider, "QA Sarcoma WGS", "QA Outsider sarcoma WGS", False),
        ]:
            contact = session.save(Q.contact.create(name=f"{owner.first_name} {owner.last_name}"), flush=True)
            seq_request = session.save(Q.seq_request.create(
                name=request_name, description=request_name, requestor=owner,
                data_delivery_mode=DataDeliveryMode.ALIGNMENT, read_type=ReadType.PAIRED_END,
                organization_contact=contact, contact_person=contact, billing_contact=contact,
                group=group if in_group else None, submission_type=SubmissionType.POOLED_LIBRARIES,
            ), flush=True)
            project = session.save(Q.project.create(
                title=title, description=None, owner_id=owner.id, group_id=group.id if in_group else None,
                status=ProjectStatus.DRAFT,
            ), flush=True)
            pool = session.save(Q.pool.create(
                name=f"{title.split()[1]}_pool_1", owner_id=owner.id, contact_name=owner.first_name,
                contact_email=owner.email, seq_request_id=seq_request.id, pool_type=PoolType.EXTERNAL, clone_number=0,
            ), flush=True)
            prefix = title.split()[1].upper()
            for i, (suffix, library_type, status, (index_name, i7, i5)) in enumerate(LIBRARIES):
                sample = session.save(Q.sample.create(
                    name=f"{prefix}_{suffix.split('_')[0]}", owner_id=owner.id, project_id=project.id, status=None,
                ), flush=True)
                library = session.save(Q.library.create(
                    name=f"{prefix}_{suffix}", sample_name=sample.name, owner_id=owner.id,
                    seq_request_id=seq_request.id, library_type=library_type, genome_ref=GenomeRef.CUSTOM,
                    service_type=ServiceType.CUSTOM, clone_number=0, status=status,
                ), flush=True)
                library.index_type = IndexType.DUAL_INDEX
                if status in (LibraryStatus.POOLED, LibraryStatus.SEQUENCED, LibraryStatus.SHARED):
                    library.pool_id = pool.id
                session.save(models.links.SampleLibraryLink(sample_id=sample.id, library_id=library.id))
                session.save(Q.library_index.create(
                    name_i7=index_name, name_i5=index_name, sequence_i7=i7, sequence_i5=i5,
                    index_kit_i7_id=None, index_kit_i5_id=None, orientation=None, library_id=library.id,
                ))
            session.flush()
        session.commit()
        print("seeded: qa.admin / qa.insider / qa.client / qa.colleague / qa.outsider @example.com, password", PASSWORD)
    finally:
        db.close_session()


if __name__ == "__main__":
    main()
