import json
from flask import url_for

from opengsync_db import categories as cats

from .TableCol import TableCol

class HTMXTable:
    columns: list[TableCol] = []
    def __init__(self, route: str, page: int | None = 0):
        self.active_search_var: str | None = None
        self.active_sort_var: str | None = None
        self.active_sort_descending: bool = False
        self.active_query_value: str | None = None
        self.filter_values: dict[str, list] = {}
        self.route = route
        self.num_pages: int | None = None
        self.active_page: int | None = page
        self.url_params: dict = {}

    def __getitem__(self, item: str) -> TableCol:
        for col in self.columns:
            if col.label == item:
                return col
        raise KeyError(f"Column with label '{item}' not found in table.")
    
    @property
    def url(self) -> str:
        state = self.url_params.copy()
        if self.num_pages is not None:
            state["page"] = self.active_page
        return url_for(self.route, **state)
    
    def get_state(self) -> dict:
        state = self.url_params.copy()
        if self.num_pages is not None:
            state["page"] = self.active_page
        if self.active_sort_var is not None:
            state["sort_by"] = self.active_sort_var
            state["sort_order"] = "desc" if self.active_sort_descending else "asc"
        if self.active_query_value is not None:
            state[self.active_search_var] = self.active_query_value
        if self.filter_values:
            for key, values in self.filter_values.items():
                state[key + "_in"] = json.dumps([v.id for v in values])
        return state
    
    def page_url(self, page: int) -> str:
        return url_for(self.route, page=page, **self.url_params)
