import json
from abc import ABC

import pandas as pd
from fastapi import Depends, Response, Request, Cookie
from loguru import logger

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ...core import exceptions as exc, dependencies
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class SelectLibrariesForm(HTMXForm, ABC):
    selected_library_ids = inputs.string.StringInputField("Selected Library IDs", hidden=True)

    def __init__(
        self,
        context: dict | None = None,
        library_status_filter: list[C.LibraryStatus] | None = None,
        library_type_filter: list[C.LibraryType] | None = None,
        selected_libraries: list[models.Library] | None = None,
        select_all_libraries: bool = False,
    ):
        context = context or {}
        HTMXForm.__init__(self)

        self._context["select_libraries"] = True

        self.library_ids = [library.id for library in selected_libraries] if selected_libraries is not None else []
        self.selected_libraries = selected_libraries or []

        self._context["select_all_libraries"] = select_all_libraries

        self._context = {**self._context, **context}

        if "pool" in context.keys():
            self._context["context"] = f"{context['pool'].name} ({context['pool'].id})"
        if "seq_request" in context.keys():
            self._context["context"] = f"{context['seq_request'].name} ({context['seq_request'].id})"
        if "experiment" in context.keys():
            self._context["context"] = f"{context['experiment'].name} ({context['experiment'].id})"
        if "lab_prep" in context.keys():
            self._context["context"] = f"{context['lab_prep'].name} ({context['lab_prep'].id})"

        if library_status_filter is not None:
            self._context["library_url_context"]["status_in"] = json.dumps([status.id for status in library_status_filter])
        if library_type_filter is not None:
            self._context["library_url_context"]["type_in"] = json.dumps([library_type.id for library_type in library_type_filter])

        self.__library_table: pd.DataFrame | None = None

    @classmethod
    def Init(
        cls,
        context: dict | None = None,
        library_status_filter: list[C.LibraryStatus] | None = None,
        library_type_filter: list[C.LibraryType] | None = None,
        selected_libraries: list[models.Library] | None = None,
        select_all_libraries: bool = False,
    ) -> FormFunc:
        def dependency() -> SelectLibrariesForm:
            return cls(
                context=context,
                library_status_filter=library_status_filter,
                library_type_filter=library_type_filter,
                selected_libraries=selected_libraries,
                select_all_libraries=select_all_libraries,
            )
        return dependency

    @htmx_route("GET")
    def Render(cls) -> RouteFunc:
        def route(
            form: "SelectLibrariesForm" = Depends(cls.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @classmethod
    def Validate(cls) -> FormFunc:
        def route(
            request: Request,
            csrf_token: str | None = Cookie(default=None),
            form: "SelectLibrariesForm" = Depends(cls.Init()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "SelectLibrariesForm":
            if request.method not in ("POST", "PUT"):
                raise exc.OpeNGSyncServerException("Form submission must be a POST or PUT request.")

            form.validate(request.state.form_data, csrf_token=csrf_token)
            selected_library_ids = form.selected_library_ids.data

            if not selected_library_ids:
                form.add_general_error("Please select at least one library.")
                raise exc.FormValidationException(form)

            if selected_library_ids:
                library_ids = json.loads(selected_library_ids)
            else:
                library_ids = []

            if len(library_ids) == 0:
                form.add_general_error("Please select at least one library.")
                raise exc.FormValidationException(form)

            form.library_ids = []
            try:
                for library_id in library_ids:
                    if not library_id:
                        continue
                    library = session.get_one(Q.library.select(id=int(library_id)))
                    form.library_ids.append(library.id)
                    form.selected_libraries.append(library)
            except ValueError:
                form.selected_library_ids.errors = ["Invalid library id"]
                raise exc.FormValidationException(form)

            library_data = dict(id=[], name=[], status_id=[])

            for library in form.selected_libraries:
                library_data["id"].append(library.id)
                library_data["name"].append(library.name)
                library_data["status_id"].append(library.status_id)

            form.__library_table = pd.DataFrame(library_data).sort_values("id")
            return form

        return route

    @property
    def library_table(self) -> pd.DataFrame:
        if self.__library_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exc.OpeNGSyncServerException("Form not validated, call .validate() first..")
        return self.__library_table

    def get_libraries(self) -> list[models.Library]:
        if self.__library_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exc.OpeNGSyncServerException("Form not validated, call .validate() first..")
        return self.selected_libraries