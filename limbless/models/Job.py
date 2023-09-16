from typing import Optional

from sqlmodel import Field, SQLModel


class Job(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, unique=True, index=True)
    slurm_id: int = Field(default=0)
    status: int = Field(default=0)
