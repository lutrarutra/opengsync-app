from datetime import datetime
from typing import Optional, TYPE_CHECKING, ClassVar

import sqlalchemy as sa
from sqlmodel import Field, SQLModel, Relationship

from ..core.categories import SeqRequestStatus, SequencingType, FlowCellType
from .Links import SeqRequestExperimentLink, SeqRequestFileLink, SeqRequestCommentLink, SeqRequestShareEmailLink

if TYPE_CHECKING:
    from .User import User
    from .Contact import Contact
    from .Library import Library
    from .Experiment import Experiment
    from .File import File
    from .Comment import Comment


class SeqRequest(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)

    name: str = Field(nullable=False, max_length=128)
    description: Optional[str] = Field(nullable=True, max_length=1024)
    status_id: int = Field(nullable=False, default=0)
    submitted_time: Optional[datetime] = Field(sa_column=sa.Column(sa.DateTime(timezone=True), nullable=True))

    technology: str = Field(nullable=False, max_length=64)
    sequencing_type_id: int = Field(nullable=False)
    num_cycles_read_1: Optional[int] = Field(nullable=True)
    num_cycles_index_1: Optional[int] = Field(nullable=True)
    num_cycles_index_2: Optional[int] = Field(nullable=True)
    num_cycles_read_2: Optional[int] = Field(nullable=True)
    read_length: Optional[int] = Field(nullable=True)
    num_lanes: Optional[int] = Field(nullable=True)
    special_requirements: Optional[str] = Field(nullable=True, max_length=512)
    sequencer: Optional[str] = Field(nullable=True, max_length=64)
    flowcell_type_id: Optional[int] = Field(nullable=True)

    organization_name: str = Field(nullable=False, max_length=128)
    organization_address: str = Field(nullable=False, max_length=256)
    organization_department: Optional[str] = Field(nullable=True, max_length=64)
    billing_code: Optional[str] = Field(nullable=True, max_length=32)

    num_libraries: int = Field(nullable=False, default=0)

    requestor_id: int = Field(nullable=False, foreign_key="lims_user.id")
    requestor: "User" = Relationship(back_populates="requests", sa_relationship_kwargs={"lazy": "joined"})

    bioinformatician_contact_id: Optional[int] = Field(nullable=True, foreign_key="contact.id")
    bioinformatician_contact: Optional["Contact"] = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "[SeqRequest.bioinformatician_contact_id]"
        },
    )

    libraries: list["Library"] = Relationship(
        back_populates="seq_request",
        sa_relationship_kwargs={"lazy": "select", "cascade": "delete"},
    )

    experiments: list["Experiment"] = Relationship(
        back_populates="seq_requests",
        link_model=SeqRequestExperimentLink,
        sa_relationship_kwargs={"lazy": "select"},
    )
    
    contact_person_id: int = Field(nullable=False, foreign_key="contact.id")
    contact_person: "Contact" = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "[SeqRequest.contact_person_id]"
        },
    )

    billing_contact_id: int = Field(nullable=False, foreign_key="contact.id")
    billing_contact: "Contact" = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "[SeqRequest.billing_contact_id]"
        },
    )

    sortable_fields: ClassVar[list[str]] = ["id", "name", "status", "requestor_id", "submitted_time", "num_libraries"]

    files: list["File"] = Relationship(
        link_model=SeqRequestFileLink, sa_relationship_kwargs={"lazy": "select", "cascade": "delete"},
    )
    comments: list["Comment"] = Relationship(
        link_model=SeqRequestCommentLink,
        sa_relationship_kwargs={"lazy": "select", "cascade": "delete"}
    )
    share_email_links: list[SeqRequestShareEmailLink] = Relationship(
        sa_relationship_kwargs={"lazy": "select", "cascade": "delete"}
    )

    seq_auth_form_file_id: Optional[int] = Field(nullable=True, default=None)

    @property
    def status(self) -> SeqRequestStatus:
        return SeqRequestStatus.get(self.status_id)
    
    @property
    def sequencing_type(self) -> SequencingType:
        return SequencingType.get(self.sequencing_type_id)
    
    @property
    def flowcell_type(self) -> Optional[FlowCellType]:
        if self.flowcell_type_id is None:
            return None
        return FlowCellType.get(self.flowcell_type_id)
    
    def is_indexed(self) -> bool:
        for library in self.libraries:
            if not library.is_indexed():
                return False
            
        return True
    
    def is_authorized(self) -> bool:
        return self.seq_auth_form_file_id is not None
    
    def is_submittable(self) -> bool:
        return self.status == SeqRequestStatus.DRAFT and self.num_libraries > 0 and self.is_authorized()
    
    def submitted_time_to_str(self) -> str:
        if self.submitted_time is None:
            return ""
        return self.submitted_time.strftime('%Y-%m-%d %H:%M')

    def to_dict(self):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.name,
            "submitted_time": self.submitted_time_to_str(),
            "requestor": self.requestor.name,
            "person_contact": f"{self.contact_person.name} ({self.contact_person.email})",
            "billing_contact": f"{self.billing_contact.name} ({self.billing_contact.email})",
            "bioinformatician_contact": f"{self.bioinformatician_contact.name} ({self.bioinformatician_contact.email})" if self.bioinformatician_contact else None,
            "num_libraries": self.num_libraries,
        }
        return data