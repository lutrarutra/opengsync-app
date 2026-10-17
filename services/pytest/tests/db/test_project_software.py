import pytest

from opengsync_db import SyncSession

from .create_units import create_project, create_user


def test_project_software_can_be_upserted_and_deleted(session: SyncSession):
    project = create_project(session, create_user(session))

    project.set_software("  ATACSeq_Pipeline  ", "v1", "initial")
    session.save(project)
    session.commit()

    project.set_software("atacseq_pipeline", "v2", "updated")
    session.save(project)
    session.commit()
    session.refresh(project)

    assert list(project.software) == ["atacseq_pipeline"]
    assert project.software["atacseq_pipeline"]["version"] == "v2"
    assert project.software["atacseq_pipeline"]["comment"] == "updated"

    project.delete_software("  ATACSEQ_PIPELINE ")
    session.save(project)
    session.commit()
    session.refresh(project)

    assert project.software == {}

    with pytest.raises(KeyError):
        project.delete_software("atacseq_pipeline")
