from typing import Optional, TYPE_CHECKING

from sqlmodel import Field, SQLModel, Relationship

from ..categories import SeqRequestStatus

if TYPE_CHECKING:
    from .User import User
    from .Contact import Contact


class SeqRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    name: str = Field(nullable=False, max_length=128)
    description: str = Field(nullable=True, max_length=1024)
    status: int = Field(nullable=False, default=0)

    requestor_id: int = Field(nullable=False, foreign_key="user.id")
    requestor: "User" = Relationship(back_populates="requests", sa_relationship_kwargs={"lazy": "joined"})

    person_contact_id: int = Field(nullable=False, foreign_key="contact.id")
    billing_contact_id: int = Field(nullable=False, foreign_key="contact.id")
    bioinformatician_contact_id: int = Field(nullable=True, foreign_key="contact.id")
    
    contact_person: "Contact" = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "[SeqRequest.person_contact_id]"
        },
    )

    billing_contact: "Contact" = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "[SeqRequest.billing_contact_id]"
        },
    )

    bioinformatician_contact: "Contact" = Relationship(
        sa_relationship_kwargs={
            "lazy": "joined",
            "foreign_keys": "[SeqRequest.bioinformatician_contact_id]"
        },
    )

    @property
    def status_type(self) -> SeqRequestStatus:
        return SeqRequestStatus.as_dict()[self.status]
