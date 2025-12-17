from typing import Literal

from dataclasses import dataclass


@dataclass
class TableCol:
    title: str
    label: str

    sort_by: str | None = None

    col_size: int = 1
    search_type: Literal["text", "number", None] = None
    sortable: bool = False
    choices: list | None = None

    def __post_init__(self):
        if self.sortable and self.sort_by is None:
            self.sort_by = self.label