import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models

from .. import logger, db
from ..core import exceptions
from ..tools.spread_sheet_components import InvalidCellValue, TextColumn, IntegerColumn
from .HTMXFlaskForm import HTMXFlaskForm
from .SpreadsheetInput import SpreadsheetInput, SpreadSheetColumn


class LibraryPropertyForm(HTMXFlaskForm):
    _template_path = "forms/library-properties.html"

    predefined_columns: list[SpreadSheetColumn] = [
        IntegerColumn("library_id", "ID", 50, required=True, read_only=True),
        TextColumn("library_name", "Library Name", 200, required=True, read_only=True)
    ]
    
    def __init__(
        self,
        editable: bool,
        project: models.Project | None,
        seq_request: models.SeqRequest | None,
        formdata: dict | None = None,
    ):
        super().__init__(formdata=formdata)
        logger.debug(formdata)
        self.project = project
        self.editable = editable
        self.seq_request = seq_request

        if self.seq_request is not None:
            self.post_url = url_for("libraries_htmx.properties", seq_request_id=self.seq_request.id)
            df = db.pd.get_library_properties(seq_request_id=self.seq_request.id)
        elif self.project is not None:
            self.post_url = url_for("libraries_htmx.properties", project_id=self.project.id)
            df = db.pd.get_library_properties(project_id=self.project.id)
        else:
            logger.error("Either project or seq_request must be provided.")
            raise ValueError("Either project or seq_request must be provided.")
        
        columns = LibraryPropertyForm.predefined_columns.copy()

        for col in df.columns:
            if col  == "library_id" or col == "library_name":
                continue
            
            if col not in [c.label for c in columns]:
                columns.append(
                    TextColumn(
                        col,
                        col.replace("_", " ").title(),
                        200,
                        max_length=1000,
                        read_only=not self.editable
                    )
                )

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=columns, csrf_token=self._csrf_token,
            post_url=self.post_url, formdata=formdata,
            allow_new_cols=self.editable,
            allow_col_rename=self.editable,
            df=df,
        )

    def validate(self) -> bool:
        if not super().validate() or self.formdata is None:
            return False
        
        if not self.spreadsheet.validate():
            return False
        
        df = self.spreadsheet.df
        
        if "library_id" not in df.columns:
            self.spreadsheet.add_general_error("Missing 'library_id' column",)
            return False
        
        if "library_name" not in df.columns:
            self.spreadsheet.add_general_error("Missing 'library_name' column",)
            return False
        
        self.df = df
        
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        for label in self.spreadsheet.columns.keys():
            if label in self.df.columns:
                continue
            for library_id in self.df["library_id"]:
                if (library := db.libraries.get(int(library_id))) is None:
                    raise exceptions.InternalServerErrorException(f"Library with ID {library_id} does not exist")
                if library.properties is None:
                    continue
                if label in library.properties:
                    library.properties.pop(label) 
        
        for idx, row in self.df.iterrows():
            if (library := db.libraries.get(row["library_id"])) is None:
                self.spreadsheet.add_error(idx, "library_id", InvalidCellValue(f"Library with ID {row['library_id']} does not exist"))
                continue
            
            if library.properties is None:
                library.properties = {}
            
            for col in self.df.columns:
                if col in ["library_id", "library_name"]:
                    continue
                
                library.properties[col] = row[col] if pd.notna(row[col]) else None

        flash("Changes Saved!", "success")
        if self.project is not None:
            return make_response(redirect=url_for("projects_page.project", project_id=self.project.id, tab="libraries-tab"))
        elif self.seq_request is not None:
            return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=self.seq_request.id, tab="request-libraries-tab"))
        else:
            logger.error("Either project or seq_request must be provided.")
            raise ValueError("Either project or seq_request must be provided.")
