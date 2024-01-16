from limbless.core import DBHandler
from limbless.categories import UserRole, SequencingType, FlowCellType
from limbless import models


def create_sample_data(db_handler: DBHandler):
    clients: list[models.User] = []

    for i in range(1, 6):
        if (client := db_handler.get_user_by_email(f"client_{i}@email.com")) is None:
            client = db_handler.create_user(
                email=f"client_{i}@email.com",
                password="password",
                first_name="Client",
                last_name=f"{i}",
                role=UserRole.CLIENT
            )
        clients.append(client)

    projects: dict[int, list[models.Project]] = {}
    samples: dict[int, list[models.Sample]] = {}
    for client in clients:
        for project_i in range(3):
            project = db_handler.create_project(
                f"Project {project_i+1}", description=f"Description {project_i}", owner_id=client.id
            )
            if client.id not in projects.keys():
                projects[client.id] = []
            projects[client.id].append(project)

            for sample_i in range(20):
                sample = db_handler.create_sample(
                    name=f"Sample {project_i * 20 + sample_i + 1}", organism_tax_id=9606 if sample_i % 2 == 0 else 10090,
                    project_id=project.id, owner_id=client.id
                )
                if client.id not in samples.keys():
                    samples[client.id] = []
                samples[client.id].append(sample)

    pools: dict[int, list[models.Pool]] = {}
    for client in clients:
        for pool_i in range(5):
            pool = db_handler.create_pool(
                name=f"Pool {pool_i+1}",
                owner_id=client.id,
                contact_name=client.name,
                contact_email=client.email,
            )
            if client.id not in pools.keys():
                pools[client.id] = []
            pools[client.id].append(pool)

        for sample in samples[client.id]:
            pool = pools[client.id][sample.id % 5]
            # db_handler.link_library_pool(
            #     pool_id=pool.id,
            #     library_id=sample.id,
            # )

    contact_person = db_handler.create_contact(
        name="Default Contact",
        email="contact@person.com",
    )

    billing_contact = db_handler.create_contact(
        name="CeMM Billing",
        email="billing@person.com",
        address="Lazarettgasse 14, 1160 Wien, Austria"
    )

    techs = ["10x 5' V2", "10x 3'", "10x 5-prime V3", "10x ATAC v2"]
    for i in range(30):
        _client_id = clients[i % len(clients)].id
        seq_request = db_handler.create_seq_request(
            name=f"Seq Request {i+1}",
            description=f"Description {i}",
            requestor_id=_client_id,
            technology=techs[i % len(techs)],
            contact_person_id=contact_person.id,
            billing_contact_id=billing_contact.id,
            seq_type=SequencingType.PAIRED_END,
            num_cycles_read_1=26,
            num_cycles_index_1=10,
            num_cycles_index_2=10,
            num_cycles_read_2=96,
            read_length=150,
            flowcell_type=FlowCellType.get(i % 5 + 1),
            sequencer="NovaSeq 6000",
            special_requirements="Please, hurry up!!!",
            organization_name="CeMM",
            organization_address="Lazarettgasse 14, 1160 Wien, Austria",
        )

        # if i > 5:
        #     for j in range(3):
        #         db_handler.link_library_seq_request(
        #             library_id=libraries[_client_id][j].id,
        #             seq_request_id=seq_request.id
        #         )

        #     if i > 10:
        #         db_handler.update_seq_request(seq_request_id=seq_request.id, status=SeqRequestStatus.SUBMITTED)
        #         if i > 28:
        #             status = SeqRequestStatus.ARCHIVED
        #         elif i > 25:
        #             status = SeqRequestStatus.FAILED
        #         elif i > 22:
        #             status = SeqRequestStatus.FINISHED
        #         elif i > 19:
        #             status = SeqRequestStatus.DATA_PROCESSING
        #         elif i > 16:
        #             status = SeqRequestStatus.SEQUENCING
        #         elif i > 13:
        #             status = SeqRequestStatus.LIBRARY_PREP
        #         else:
        #             continue

        #         db_handler.update_seq_request(seq_request_id=seq_request.id, status=status)