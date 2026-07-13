import json
from abc import ABC

import pandas as pd
from fastapi import Depends, Response, Request, Cookie
from loguru import logger

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ...core import exceptions as exc, dependencies
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class SelectPoolsForm(HTMXForm, ABC):
    selected_pool_ids = inputs.string.StringInputField("Selected Pool IDs", hidden=True)

    def __init__(
        self,
        context: dict | None = None,
        pool_status_filter: list[C.PoolStatus] | None = None,
        selected_pools: list[models.Pool] | None = None,
    ):
        context = context or {}
        HTMXForm.__init__(self)

        self._context["select_pools"] = True

        self.pool_ids = [pool.id for pool in selected_pools] if selected_pools is not None else []
        self.selected_pools = selected_pools or []

        self._context = {**self._context, **context}

        if "pool" in context.keys():
            self._context["context"] = f"{context['pool'].name} ({context['pool'].id})"
        if "seq_request" in context.keys():
            self._context["context"] = f"{context['seq_request'].name} ({context['seq_request'].id})"
        if "experiment" in context.keys():
            self._context["context"] = f"{context['experiment'].name} ({context['experiment'].id})"
        if "lab_prep" in context.keys():
            self._context["context"] = f"{context['lab_prep'].name} ({context['lab_prep'].id})"

        if pool_status_filter is not None:
            self._context["pool_url_context"]["status_in"] = json.dumps([status.id for status in pool_status_filter])

        self.__pool_table: pd.DataFrame | None = None

    @classmethod
    def Init(
        cls,
        context: dict | None = None,
        pool_status_filter: list[C.PoolStatus] | None = None,
        selected_pools: list[models.Pool] | None = None,
    ) -> FormFunc:
        def dependency() -> SelectPoolsForm:
            return cls(
                context=context,
                pool_status_filter=pool_status_filter,
                selected_pools=selected_pools,
            )
        return dependency

    @htmx_route("GET")
    def Render(cls) -> RouteFunc:
        def route(
            form: "SelectPoolsForm" = Depends(cls.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @classmethod
    def Validate(cls) -> FormFunc:
        def route(
            request: Request,
            csrf_token: str | None = Cookie(default=None),
            form: "SelectPoolsForm" = Depends(cls.Init()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "SelectPoolsForm":
            if request.method not in ("POST", "PUT"):
                raise exc.OpeNGSyncServerException("Form submission must be a POST or PUT request.")

            form.validate(request.state.form_data, csrf_token=csrf_token)
            selected_pool_ids = form.selected_pool_ids.data

            if not selected_pool_ids:
                form.add_general_error("Please select at least one pool.")
                raise exc.FormValidationException(form)

            if selected_pool_ids:
                pool_ids = json.loads(selected_pool_ids)
            else:
                pool_ids = []

            if len(pool_ids) == 0:
                form.add_general_error("Please select at least one pool.")
                raise exc.FormValidationException(form)

            form.pool_ids = []
            try:
                for pool_id in pool_ids:
                    if not pool_id:
                        continue
                    pool = session.get_one(Q.pool.select(id=int(pool_id)))
                    form.pool_ids.append(pool.id)
                    form.selected_pools.append(pool)
            except ValueError:
                form.selected_pool_ids.errors = ["Invalid pool id"]
                raise exc.FormValidationException(form)

            pool_data = dict(id=[], name=[], status_id=[])

            for pool in form.selected_pools:
                pool_data["id"].append(pool.id)
                pool_data["name"].append(pool.name)
                pool_data["status_id"].append(pool.status_id)

            form.__pool_table = pd.DataFrame(pool_data).sort_values("id")
            return form

        return route

    @property
    def pool_table(self) -> pd.DataFrame:
        if self.__pool_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exc.OpeNGSyncServerException("Form not validated, call .validate() first..")
        return self.__pool_table

    def get_pools(self) -> list[models.Pool]:
        if self.__pool_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exc.OpeNGSyncServerException("Form not validated, call .validate() first..")
        return self.selected_pools