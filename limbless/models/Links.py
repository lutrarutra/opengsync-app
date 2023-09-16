from typing import Optional, List

from sqlmodel import Field, SQLModel

from ..categories import AccessType, UserResourceRelation


class LibrarySeqRequestLink(SQLModel, table=True):
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )
    seq_request_id: int = Field(
        foreign_key="seqrequest.id", primary_key=True
    )


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
    # TODO: rename to 'relation'
    relation_id: int = Field(
        nullable=False
    )

    @property
    def relation(self) -> UserResourceRelation:
        return UserResourceRelation.as_dict()[self.relation_id]

    @property
    def access_type(self) -> Optional[List[AccessType]]:
        access = []
        project_role = self.relation
        if project_role == UserResourceRelation.OWNER:
            access.append(AccessType.WRITE)
            access.append(AccessType.READ)
        elif project_role == UserResourceRelation.CONTRIBUTOR:
            access.apppend(AccessType.WRITE)
            access.apppend(AccessType.READ)
        elif project_role == UserResourceRelation.VIEWER:
            access.append(AccessType.READ)

        if len(access) == 0:
            return None

        return access


class LibraryUserLink(SQLModel, table=True):
    library_id: int = Field(
        foreign_key="library.id", primary_key=True
    )
    user_id: int = Field(
        foreign_key="user.id", primary_key=True
    )
    relation_id: int = Field(
        nullable=False
    )

    @property
    def relation(self) -> UserResourceRelation:
        return UserResourceRelation.as_dict()[self.relation_id]

    @property
    def access_type(self) -> Optional[list[AccessType]]:
        access = []
        project_role = self.relation
        if project_role == UserResourceRelation.OWNER:
            access.append(AccessType.WRITE)
            access.append(AccessType.READ)
        elif project_role == UserResourceRelation.CONTRIBUTOR:
            access.apppend(AccessType.WRITE)
            access.apppend(AccessType.READ)
        elif project_role == UserResourceRelation.VIEWER:
            access.append(AccessType.READ)

        if len(access) == 0:
            return None

        return access
