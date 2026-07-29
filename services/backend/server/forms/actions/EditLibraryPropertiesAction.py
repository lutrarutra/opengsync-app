from typing import Sequence
import pandas as pd

from pydantic import BaseModel
from fastapi import Depends, Query
from fastapi.responses import Response

from opengsync_db import models, SyncSession, queries as Q, categories as C

from ...core import exceptions as exc, responses, dependencies
from ...utils import parsing
from ...components import inputs
from ...components.tables import IntegerColumn, TextColumn
from ..HTMXForm import HTMXForm, htmx_route, FormFunc, RouteFunc


class EditLibraryPropertiesAction(HTMXForm):
    template_path = "actions/edit-library-properties.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            IntegerColumn("library_id", "ID", 50, read_only=True),
            TextColumn("library_name", "Library Name", 200, read_only=True),
        ],
        allow_new_rows=False,
        allow_new_cols=True,
        allow_col_rename=True,
    )

    def __init__(
        self,
        access_level: C.AccessLevel,
        seq_request_id: int | None,
        project_id: int | None,
        library_id: int | None,
        libraries: Sequence[models.Library] | None = None,
    ) -> None:
        super().__init__()
        self._validated_df: pd.DataFrame | None = None
        self._to_delete: set[str] = set()
        self.access_level = access_level
        self.libraries = libraries
        query_params = {}
        if seq_request_id is not None:
            query_params["seq_request_id"] = seq_request_id
        if project_id is not None:
            query_params["project_id"] = project_id
        if library_id is not None:
            query_params["library_id"] = library_id

        self.seq_request_id = seq_request_id
        self.project_id = project_id
        self.library_id = library_id
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit").include_query_params(**query_params)

        if self.libraries is not None:
            all_property_keys: set[str] = set()
            for library in self.libraries:
                if library.properties:
                    all_property_keys.update(library.properties.keys())

            rows: list[dict] = []
            for library in self.libraries:
                row: dict = {
                    "library_id": library.id,
                    "library_name": library.name,
                }
                for key in all_property_keys:
                    row[key] = library.properties.get(key) if library.properties else None
                rows.append(row)

            columns = ["library_id", "library_name", *sorted(all_property_keys)]
            df = pd.DataFrame(rows, columns=columns)
        else:
            df = pd.DataFrame(columns=["library_id", "library_name"])

        for col in df.columns:
            if col not in self.spreadsheet.columns.keys():
                self.spreadsheet.add_column(
                    TextColumn(
                        col,
                        col.replace("_", " ").title(),
                        200,
                        max_length=1000,
                        read_only=self.access_level < C.AccessLevel.WRITE,
                        can_be_deleted=self.access_level >= C.AccessLevel.WRITE,
                    )
                )
        from loguru import logger
        logger.debug(df)

        self.spreadsheet.configure(df=df, post_url=self.post_url, csrf_token=self.csrf_token_value)
    
    @classmethod
    def Init(cls) -> FormFunc:
        def form(
            library_id: int | None = Query(None),
            seq_request_id: int | None = Query(None),
            project_id: int | None = Query(None),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ):
            libraries = session.get_all(Q.library.select(seq_request_id=seq_request_id, project_id=project_id, id=library_id).order_by(models.Library.id.asc()))

            if library_id is not None:
                access_level = session.get_access_level(Q.library.permissions(library_id=library_id, user_id=current_user.id))
            elif seq_request_id is not None:
                access_level = session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id))
            elif project_id is not None:
                access_level = session.get_access_level(Q.project.permissions(project_id=project_id, user_id=current_user.id))
            else:
                raise exc.BadRequestException("Must provide at least one of seq_request_id, project_id, or library_id")
            
            if access_level < C.AccessLevel.READ:
                raise exc.NoPermissionsException("You do not have permission to view library properties.")
            form = EditLibraryPropertiesAction(access_level=access_level, seq_request_id=seq_request_id, project_id=project_id, library_id=library_id, libraries=libraries)
            return form
        return form
    
    @htmx_route("GET")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "EditLibraryPropertiesAction" = Depends(EditLibraryPropertiesAction.Init()),
        ):
            return form.make_response()
        return route
            

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "EditLibraryPropertiesAction" = Depends(EditLibraryPropertiesAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            df = form.spreadsheet.data

            if form.access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit library properties.")

            flash = responses.flash("Changes Saved!", "success")

            for label in form._to_delete:
                for library_id in df["library_id"]:
                    if library_id:
                        library = session.get_one(Q.library.select(id=int(library_id)))
                        if library.properties and label in library.properties:
                            library.properties.pop(label)

            class RowSchema(BaseModel):
                library_id: int
                library_name: str | None

            for idx, row in parsing.safe_iter(df, RowSchema):
                library = session.get_one(Q.library.select(id=row.library_id))
                if library.properties is None:
                    library.properties = {}
                
                for col in df.columns:
                    if col in ("library_id", "library_name"):
                        continue
                    
                    val = df.at[idx, col]
                    if val is not None and not pd.isna(val) and str(val).strip():
                        library.properties[col] = str(val).strip()
                    else:
                        library.properties[col] = None

                for col in list(library.properties.keys()):
                    if col not in df.columns:
                        library.properties.pop(col)

            if form.seq_request_id is not None:
                return responses.htmx_response(
                    redirect=responses.url_for("seq_request_page", seq_request_id=form.seq_request_id).include_query_params(tab="request-libraries-tab"),
                    flash=flash,
                )
            elif form.project_id is not None:
                return responses.htmx_response(
                    redirect=responses.url_for("project_page", project_id=form.project_id).include_query_params(tab="libraries-tab"),
                    flash=flash,
                )
            elif form.library_id is not None:
                return responses.htmx_response(redirect=responses.url_for("library_page", library_id=form.library_id), flash=flash)
            else:
                raise exc.OpeNGSyncServerException("No seq_request or project provided.")
            
        return route
