import json
from abc import ABC

import pandas as pd
from fastapi import Depends, Response, Request, Cookie
from loguru import logger

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ...core import exceptions as exc, dependencies
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class SelectSamplesForm(HTMXForm, ABC):
    selected_sample_ids = inputs.string.StringInputField("Selected Sample IDs", hidden=True)

    def __init__(
        self,
        context: dict | None = None,
        sample_status_filter: list[C.SampleStatus] | None = None,
        selected_samples: list[models.Sample] | None = None,
        select_all_samples: bool = False,
    ):
        context = context or {}
        HTMXForm.__init__(self)

        self._context["select_samples"] = True

        self.sample_ids = [sample.id for sample in selected_samples] if selected_samples is not None else []
        self.selected_samples = selected_samples or []
        self._context["select_all_samples"] = select_all_samples

        if sample_status_filter is not None:
            self._context["sample_url_context"]["status_in"] = json.dumps([status.id for status in sample_status_filter])

        self.__sample_table: pd.DataFrame | None = None

    @classmethod
    def Init(
        cls,
        context: dict | None = None,
        sample_status_filter: list[C.SampleStatus] | None = None,
        selected_samples: list[models.Sample] | None = None,
        select_all_samples: bool = False,
    ) -> FormFunc:
        def dependency() -> SelectSamplesForm:
            return cls(
                context=context,
                sample_status_filter=sample_status_filter,
                selected_samples=selected_samples,
                select_all_samples=select_all_samples,
            )
        return dependency

    @htmx_route("GET")
    def Render(cls) -> RouteFunc:
        def route(
            form: "SelectSamplesForm" = Depends(cls.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @classmethod
    def Validate(cls) -> FormFunc:
        def route(
            request: Request,
            csrf_token: str | None = Cookie(default=None),
            form: "SelectSamplesForm" = Depends(cls.Init()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "SelectSamplesForm":
            if request.method not in ("POST", "PUT"):
                raise exc.OpeNGSyncServerException("Form submission must be a POST or PUT request.")

            form.validate(request.state.form_data, csrf_token=csrf_token)
            selected_sample_ids = form.selected_sample_ids.data

            if not selected_sample_ids:
                form.add_general_error("Please select at least one sample.")
                raise exc.FormValidationException(form)

            if selected_sample_ids:
                sample_ids = json.loads(selected_sample_ids)
            else:
                sample_ids = []

            if len(sample_ids) == 0:
                form.add_general_error("Please select at least one sample.")
                raise exc.FormValidationException(form)

            form.sample_ids = []
            try:
                for sample_id in sample_ids:
                    if not sample_id:
                        continue
                    sample = session.get_one(Q.sample.select(id=int(sample_id)))
                    form.sample_ids.append(sample.id)
                    form.selected_samples.append(sample)
            except ValueError:
                form.selected_sample_ids.errors = ["Invalid sample id"]
                raise exc.FormValidationException(form)

            sample_data = dict(id=[], name=[], status_id=[])

            for sample in form.selected_samples:
                sample_data["id"].append(sample.id)
                sample_data["name"].append(sample.name)
                sample_data["status_id"].append(sample.status_id)

            form.__sample_table = pd.DataFrame(sample_data).sort_values("id")
            return form

        return route

    @property
    def sample_table(self) -> pd.DataFrame:
        if self.__sample_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exc.OpeNGSyncServerException("Form not validated, call .validate() first..")
        return self.__sample_table

    def get_samples(self) -> list[models.Sample]:
        if self.__sample_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exc.OpeNGSyncServerException("Form not validated, call .validate() first..")
        return self.selected_samples