from typing import Sequence
import pandas as pd
from fastapi import Request, Depends, Query
from fastapi.responses import Response

from opengsync_db import models, AsyncSession, queries as Q, categories as C

from ..core import exceptions as exc, responses, dependencies
from ..components import inputs
from ..components.tables import IntegerColumn, TextColumn
from .HTMXForm import HTMXForm


class LibraryPropertyForm(HTMXForm):
    template_path = "forms/library-properties.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        IntegerColumn("library_id", "ID", 50, read_only=True),
        TextColumn("library_name", "Library Name", 200, read_only=True),
    ])

    def __init__(
        self,
        request: Request,
        access_level: C.AccessLevel,
        seq_request_id: int | None,
        project_id: int | None,
        library_id: int | None,
        libraries: Sequence[models.Library] | None = None,
    ) -> None:
        super().__init__(request)
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
        self.post_url = request.url_for("edit_library_properties").include_query_params(**query_params)

        editable = self.access_level >= C.AccessLevel.WRITE

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

        self.spreadsheet.configure(
            df=df,
            post_url=self.post_url,
            csrf_token=self.csrf_token_value,
            editable=editable,
            allow_new_cols=editable,
            allow_col_rename=editable,
        )

    async def validate(self) -> bool:
        """Validate the submitted spreadsheet via the SpreadsheetInputField."""
        await super().validate()
        df = self.spreadsheet.data

        if "library_id" not in df.columns or "library_name" not in df.columns:
            self.spreadsheet._errors.append("Missing required columns.")
            return False

        self._validated_df = df
        self._to_delete = self.spreadsheet.to_delete
        return True

    @staticmethod
    async def edit(
        request: Request,
        project_id: int | None = Query(None),
        seq_request_id: int | None = Query(None),
        library_id: int | None = Query(None),
        current_user: models.User = Depends(dependencies.require_user),
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        access_level: C.AccessLevel = C.AccessLevel.NONE

        form = LibraryPropertyForm(request, access_level=access_level, seq_request_id=seq_request_id, project_id=project_id, library_id=library_id)
        await form.validate()

        df = form.spreadsheet.data
        assert df is not None

        flash = responses.flash("Changes Saved!", "success")

        for label in form._to_delete:
            for library_id in df["library_id"]:
                if library_id:
                    if await session.get_access_level(Q.library.permissions(library_id=int(library_id), user_id=current_user.id)) < C.AccessLevel.WRITE:
                        flash = responses.flash("You do not have permission to edit some of the libraries..", "warning")
                        continue
                    library = await session.get_one(Q.library.select(id=int(library_id)))
                    if library.properties and label in library.properties:
                        library.properties.pop(label, None)

        for _, row in df.iterrows():
            library = await session.get_one(Q.library.select(id=int(row["library_id"])))
            if await session.get_access_level(Q.library.permissions(library_id=int(row["library_id"]), user_id=current_user.id)) < C.AccessLevel.WRITE:
                flash = responses.flash("You do not have permission to edit some of the libraries..", "warning")
                continue
            if library.properties is None:
                library.properties = {}
            for col in df.columns:
                if col in ("library_id", "library_name"):
                    continue
                val = row[col]
                if val is not None and not pd.isna(val) and str(val).strip():
                    library.properties[col] = str(val).strip()
                else:
                    library.properties[col] = None

        if seq_request_id is not None:
            return await responses.htmx_response(
                redirect=responses.url_for("seq_request_page", seq_request_id=seq_request_id).include_query_params(tab="request-libraries-tab"),
                flash=flash,
            )
        elif project_id is not None:
            return await responses.htmx_response(
                redirect=responses.url_for("project_page", project_id=project_id).include_query_params(tab="libraries-tab"),
                flash=flash,
            )
        elif library_id is not None:
            return await responses.htmx_response(redirect=responses.url_for("library_page", library_id=library_id), flash=flash)
        else:
            raise exc.OpeNGSyncServerException("No seq_request or project provided.")
