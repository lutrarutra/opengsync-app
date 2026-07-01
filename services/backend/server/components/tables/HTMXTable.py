import json
from starlette.datastructures import URL
from fastapi import Response

from opengsync_db import utils

from .TableCol import TableCol
from ...core import responses, context

class HTMXTable:
    template = ""
    columns: list[TableCol] = []
    def __init__(self, route: str, page: int | None = 0, order_by: utils.OrderBy | None = None):
        self.active_search_var: str | None = None
        self.active_sort_var: str | None = None
        self.active_sort_descending: bool = False
        self.active_query_value: str | None = None
        self.filter_values: dict[str, list] = {}
        self.route = route
        self.num_pages: int | None = None
        self.active_page: int | None = page
        self.url_params: dict = {}
        self.context: dict = {}

        if order_by is not None:
            try:
                attr = getattr(order_by.element, "key", getattr(order_by.element, "name", None))
                if attr is not None:
                    self.active_sort_var = attr
                    is_desc = getattr(order_by.modifier, "__name__", "") == "desc_op"
                    self.active_sort_descending = is_desc
                    self.url_params["order_by"] = f"{attr}:{'desc' if is_desc else 'asc'}"
            except AttributeError:
                pass

    def __getitem__(self, item: str) -> TableCol:
        for col in self.columns:
            if col.label == item:
                return col
        raise KeyError(f"Column with label '{item}' not found in table.")
    
    @property
    def url(self) -> URL:
        return context.ctx.request.url_for(self.route).include_query_params(**self.url_params)
    
    def get_state(self) -> dict:
        state = self.url_params.copy()
        if self.num_pages is not None:
            state["page"] = self.active_page
        if self.active_sort_var is not None:
            state["order_by"] = f"{self.active_sort_var}:{'desc' if self.active_sort_descending else 'asc'}"
        if self.active_query_value is not None:
            state[self.active_search_var] = self.active_query_value
        if self.filter_values:
            for key, values in self.filter_values.items():
                state[key + "_in"] = json.dumps([v.id for v in values])
        return state
    
    def page_url(self, page: int) -> URL:
        return context.ctx.request.url_for(self.route).include_query_params(**{**self.url_params, "page": page})

    def set_num_pages(self, count: int, limit: int = 10) -> None:
        self.num_pages = (count + limit - 1) // limit

    async def make_response(self, **kwargs) -> Response:
        if not self.template:
            raise ValueError("Template not set for HTMXTable.")
        return await responses.htmx_response(template=self.template, table=self, **{**self.context, **kwargs})