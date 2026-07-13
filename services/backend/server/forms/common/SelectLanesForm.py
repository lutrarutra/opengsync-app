import json
from abc import ABC

import pandas as pd
from fastapi import Depends, Response, Request, Cookie
from loguru import logger

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ...core import exceptions as exc, dependencies
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class SelectLanesForm(HTMXForm, ABC):
    selected_lane_ids = inputs.string.StringInputField("Selected Lane IDs", hidden=True)

    def __init__(
        self,
        context: dict | None = None,
        selected_lanes: list[models.Lane] | None = None,
    ):
        context = context or {}
        HTMXForm.__init__(self)

        self._context["select_lanes"] = True

        self.lane_ids = [lane.id for lane in selected_lanes] if selected_lanes is not None else []
        self.selected_lanes = selected_lanes or []

        self._context = {**self._context, **context}

        if "pool" in context.keys():
            self._context["context"] = f"{context['pool'].name} ({context['pool'].id})"
        if "seq_request" in context.keys():
            self._context["context"] = f"{context['seq_request'].name} ({context['seq_request'].id})"
        if "experiment" in context.keys():
            self._context["context"] = f"{context['experiment'].name} ({context['experiment'].id})"
        if "lab_prep" in context.keys():
            self._context["context"] = f"{context['lab_prep'].name} ({context['lab_prep'].id})"

        self.__lane_table: pd.DataFrame | None = None

    @classmethod
    def Init(
        cls,
        context: dict | None = None,
        selected_lanes: list[models.Lane] | None = None,
    ) -> FormFunc:
        def dependency() -> SelectLanesForm:
            return cls(
                context=context,
                selected_lanes=selected_lanes,
            )
        return dependency

    @htmx_route("GET")
    def Render(cls) -> RouteFunc:
        def route(
            form: "SelectLanesForm" = Depends(cls.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @classmethod
    def Validate(cls) -> FormFunc:
        def route(
            request: Request,
            csrf_token: str | None = Cookie(default=None),
            form: "SelectLanesForm" = Depends(cls.Init()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "SelectLanesForm":
            if request.method not in ("POST", "PUT"):
                raise exc.OpeNGSyncServerException("Form submission must be a POST or PUT request.")

            form.validate(request.state.form_data, csrf_token=csrf_token)
            selected_lane_ids = form.selected_lane_ids.data

            if not selected_lane_ids:
                form.add_general_error("Please select at least one lane.")
                raise exc.FormValidationException(form)

            if selected_lane_ids:
                lane_ids = json.loads(selected_lane_ids)
            else:
                lane_ids = []

            if len(lane_ids) == 0:
                form.add_general_error("Please select at least one lane.")
                raise exc.FormValidationException(form)

            form.lane_ids = []
            try:
                for lane_id in lane_ids:
                    if not lane_id:
                        continue
                    lane = session.get_one(Q.lane.select(id=int(lane_id)))
                    form.lane_ids.append(lane.id)
                    form.selected_lanes.append(lane)
            except ValueError:
                form.selected_lane_ids.errors = ["Invalid lane id"]
                raise exc.FormValidationException(form)

            lane_data = dict(id=[], name=[], status_id=[])

            for lane in form.selected_lanes:
                lane_data["id"].append(lane.id)
                lane_data["name"].append(f"{lane.experiment.name}-L{lane.number}")
                lane_data["status_id"].append(None)

            form.__lane_table = pd.DataFrame(lane_data).sort_values("id")
            return form

        return route

    @property
    def lane_table(self) -> pd.DataFrame:
        if self.__lane_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exc.OpeNGSyncServerException("Form not validated, call .validate() first..")
        return self.__lane_table

    def get_lanes(self) -> list[models.Lane]:
        if self.__lane_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exc.OpeNGSyncServerException("Form not validated, call .validate() first..")
        return self.selected_lanes