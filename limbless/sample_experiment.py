from limbless.core import DBHandler
from limbless import categories


def create_sample_experiment(db_handler: DBHandler):
    if (user := db_handler.get_user_by_email("test@user.com")) is None:
        user = db_handler.create_user(
            email="test@user.com",
            password="password",
            role=categories.UserRole.ADMIN
        )

    projects = []
    for i in range(10):
        if (project := db_handler.get_project(i + 1)) is None:
            project = db_handler.create_project(
                name=f"Project_{i+1:02d}",
                description=f"Project_{i+1:02d} description"
            )
            db_handler.link_project_user(project.id, user.id, categories.ProjectRole.OWNER)

        projects.append(project)

    if db_handler.get_organism(9606) is None:
        db_handler.create_organism(
            tax_id=9606,
            scientific_name="Homo sapiens",
            common_name="human",
            category=categories.OrganismCategory.EUKARYOTA,
        )

    if db_handler.get_organism(10090) is None:
        db_handler.create_organism(
            tax_id=10090,
            scientific_name="Mus musculus",
            common_name="house mouse",
            category=categories.OrganismCategory.EUKARYOTA,
        )

    samples = []
    for i in range(200):
        if (sample := db_handler.get_sample(i + 1)) is None:
            sample = db_handler.create_sample(
                f"Sample_{i+1:02d}",
                9606 if i < 100 else 10090,
                projects[i % len(projects)].id,
            )
        samples.append(sample)

    libs = []
    for i in range(20):
        if (library := db_handler.get_library(i + 1)) is None:
            library = db_handler.create_library(
                f"Library_{i+1:02d}",
                categories.LibraryType.SC_RNA,
                (i % 5) + 1,
            )

        libs.append(library)

    # n_seqindices = db_handler.get_num_seqindices()
    # for i, sample in enumerate(samples):

    experiments = []
    for i in range(10):
        if (experiment := db_handler.get_experiment(i + 1)) is None:
            experiment = db_handler.create_experiment(
                f"Experiment_{i+1:02d}",
                f"Flowcell_{i+1:02d}"
            )
        experiments.append(experiment)

    runs = []
    for i, experiment in enumerate(experiments):
        runs.append(
            db_handler.create_run(
                1, experiment.id, 1, 2, 3, 4,
            )
        )
        # if i % 2 == 0:
        #     runs.append(
        #         db_handler.create_run(
        #             2, experiment.id, 1, 2, 3, 4,
        #         )
        #     )

    # for i, library in enumerate(libs):
    #     db_handler.link_run_library(runs[i % len(runs)].id, library.id)
