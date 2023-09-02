from typing import List, Optional

from sqlmodel import Field, Relationship, SQLModel

class LibrarySampleLink(SQLModel, table=True):
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )
    sample_id: int = Field(
        foreign_key="sample.id", primary_key=True
    )
    seq_index_id: int = Field(
        foreign_key="seqindex.id", primary_key=True
    )
    # seq_index_type: int = Field(nullable=False, primary_key=True)


class RunLibraryLink(SQLModel, table=True):
    run_id: int = Field(
        foreign_key="run.id", primary_key=True
    )
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )

class ProjectUserLink(SQLModel, table=True):
    project_id: int = Field(
        foreign_key="project.id", primary_key=True
    )
    user_id: int = Field(
        foreign_key="user.id", primary_key=True
    )
    role: int = Field(nullable=False)
