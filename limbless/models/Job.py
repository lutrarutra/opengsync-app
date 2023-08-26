from typing import Optional
from enum import Enum

from sqlmodel import Field, SQLModel

class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False, max_length=64, unique=True, index=True)
    slurm_id: int = Field(default=0)
    status: int = Field(default=0)


class JobStatus(Enum):
    WAITING = 0
    QUEUED = 1
    RUNNING = 2
    FINISHED = 3
    ERRORED = 4

    @staticmethod
    def is_valid_status(status: int):
        return status in [s.value for s in JobStatus]