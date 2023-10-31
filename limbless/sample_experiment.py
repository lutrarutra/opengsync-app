from limbless.core import DBHandler
from limbless.categories import UserRole, LibraryType
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

    libraries: dict[int, list[models.Library]] = {}
    for client in clients:
        for library_i in range(5):
            library = db_handler.create_library(
                name=f"Library {library_i+1}",
                library_type=LibraryType.SC_ATAC if library_i % 2 == 0 else LibraryType.SC_RNA,
                owner_id=client.id,
                index_kit_id=None
            )
            if client.id not in libraries.keys():
                libraries[client.id] = []
            libraries[client.id].append(library)

        for sample in samples[client.id]:
            library = libraries[client.id][sample.id % 5]
            db_handler.link_library_sample(
                library_id=library.id,
                sample_id=sample.id,
                seq_index_id=None
            )

