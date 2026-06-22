import json

import pandas as pd
from fastapi import Request
from fastapi.responses import Response

from opengsync_db import models, AsyncSession, queries as Q, categories as C

from ..core import exceptions as exc, responses
from ..components import inputs
from ..components.tables.spreadsheet import IntegerColumn, TextColumn
from .HTMXForm import HTMXForm


class LibraryPropertyForm(HTMXForm):
    template_path = "forms/library-properties.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField()

    def __init__(
        self,
        request: Request,
        access_level: C.AccessLevel,
        seq_request: models.SeqRequest | None = None,
        project: models.Project | None = None,
        df: pd.DataFrame | None = None,
    ) -> None:
        super().__init__(request)
        self.seq_request = seq_request
        self.project = project
        self._df = df
        self._validated_df: pd.DataFrame | None = None
        self._to_delete: set[str] = set()
        self.access_level = access_level

    async def prepare(self):
        """Configure the spreadsheet field before rendering."""
        if self.seq_request is not None:
            post_url = str(
                self.request.url_for(
                    "add_library_properties", seq_request_id=self.seq_request.id
                )
            )
            async with self.request.app.state.db_handler.get_session() as session:
                df = await session.pd.get_library_properties(
                    seq_request_id=self.seq_request.id
                )
        elif self.project is not None:
            post_url = str(
                self.request.url_for(
                    "add_project_library_properties", project_id=self.project.id
                )
            )
            async with self.request.app.state.db_handler.get_session() as session:
                df = await session.pd.get_library_properties(
                    project_id=self.project.id
                )
        else:
            raise exc.OpeNGSyncServerException(
                "Either seq_request or project must be provided."
            )
        editable = self.access_level >= C.AccessLevel.WRITE

        predefined = [
            IntegerColumn("library_id", "ID", 50, read_only=True),
            TextColumn("library_name", "Library Name", 200, read_only=True),
        ]

        self.spreadsheet.configure(
            df=df,
            post_url=post_url,
            csrf_token=self.csrf_token.data or "",
            editable=editable,
            predefined_columns=predefined,
            allow_new_cols=editable,
            allow_col_rename=editable,
        )

    async def validate(self) -> bool:
        """Parse spreadsheet JSON submitted by the JS Handsontable editor."""
        await super().validate()

        form_data = await self.request.form()
        spreadsheet_json_raw = form_data.get("spreadsheet")
        columns_json_raw = form_data.get("columns")

        spreadsheet_json = (
            str(spreadsheet_json_raw) if spreadsheet_json_raw is not None else None
        )
        columns_json = str(columns_json_raw) if columns_json_raw is not None else None

        if not spreadsheet_json or not columns_json:
            return False

        col_names = json.loads(columns_json)
        data = json.loads(spreadsheet_json)

        col_title_map = {
            col.name: col.label for col in self.spreadsheet.columns.values()
        }

        df = pd.DataFrame(
            data,
            columns=[
                col_title_map.get(c, c.lower().replace(" ", "_")) for c in col_names
            ],
        )
        df = df.replace(r"^\s*$", "", regex=True)
        df = df.dropna(how="all")

        if "library_id" not in df.columns or "library_name" not in df.columns:
            self.spreadsheet._errors.append("Missing required columns.")
            return False

        to_delete: set[str] = set()
        for label, col in self.spreadsheet.columns.items():
            if col.can_be_deleted and label not in df.columns:
                to_delete.add(label)

        for label, col in self.spreadsheet.columns.items():
            if label not in df.columns:
                continue
            try:
                col.validate(df[label].tolist(), df[label].tolist())
            except Exception as e:
                self.spreadsheet._errors.append(f"Validation error in '{label}': {e}")

        if self.spreadsheet._errors:
            return False

        self._validated_df = df
        self._to_delete = to_delete
        return True

    async def save(self, session: AsyncSession) -> Response:
        """Save the validated spreadsheet data."""
        if not await self.validate():
            return await self.make_response()

        df = self._validated_df
        assert df is not None

        for label in self._to_delete:
            for library_id in df["library_id"]:
                if library_id:
                    library = await session.get_one(
                        Q.library.select(id=int(library_id))
                    )
                    if library.properties and label in library.properties:
                        library.properties.pop(label, None)

        for _, row in df.iterrows():
            library = await session.get_one(Q.library.select(id=int(row["library_id"])))
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

        if self.seq_request is not None:
            return await responses.htmx_response(
                redirect=responses.url_for(
                    "seq_request_page",
                    seq_request_id=self.seq_request.id,
                    tab="request-libraries-tab",
                ),
                flash=responses.flash("Changes Saved!", "success"),
            )
        elif self.project is not None:
            return await responses.htmx_response(
                redirect=responses.url_for(
                    "project_page",
                    project_id=self.project.id,
                    tab="libraries-tab",
                ),
                flash=responses.flash("Changes Saved!", "success"),
            )
        else:
            raise exc.OpeNGSyncServerException("No seq_request or project provided.")
