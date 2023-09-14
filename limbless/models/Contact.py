from typing import Optional

from sqlmodel import Field, SQLModel


class Contact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=128)
    organization: str = Field(nullable=True, max_length=128)
    email: str = Field(nullable=True, max_length=128)
    phone: str = Field(nullable=True, max_length=16)
    billing_code: str = Field(nullable=True, max_length=32)
    address: str = Field(nullable=True, max_length=256)
