from limbless import models

def create_sample_experiment(db_handler):
    user = db_handler.create_user(
        email="artur.gynter@hotmail.com",
        password="password",
        role=models.UserRole.ADMIN
    )
    projects = [
        db_handler.create_project(
            name=f"Project_{i+1:02d}",
            description=f"Project_{i+1:02d} description"
        ) for i in range(10)
    ]

    for project in projects:
        db_handler.link_project_user(project.id, user.id, models.ProjectRole.OWNER)

    samples = [
        db_handler.create_sample(
            f"Sample_{i+1:02d}",
            "human" if i < 100 else "mouse",
            projects[i % len(projects)].id,
            f"index1_{i+1:02d}",
            f"index2_{i+1:02d}"
        ) for i in range(200)
    ]

    libs = [
        db_handler.create_library(
            f"Library_{i+1:02d}",
            models.LibraryType.TRANSCRIPTOME
        ) for i in range(20)
    ]

    for i, sample in enumerate(samples):
        db_handler.link_library_sample(libs[i % len(libs)].id, sample.id)


    experiments = [
        db_handler.create_experiment(
            f"Experiment_{i+1:02d}",
            f"Flowcell_{i+1:02d}"
        ) for i in range(10)
    ]

    runs = []
    for i, experiment in enumerate(experiments):
        runs.append(
            db_handler.create_run(
                1,experiment.id,1,2,3,4,
            )
        )    
        if i % 2 == 0:
            runs.append(
                db_handler.create_run(
                    2,experiment.id,1,2,3,4,
                )
            )
    
    for i, library in enumerate(libs):
        db_handler.link_run_library(runs[i % len(runs)].id, library.id)