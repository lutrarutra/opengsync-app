import os
from typing import Literal
from uuid import uuid4
import json

import pandas as pd
import numpy as np

from flask import Response, current_app, url_for, flash
from flask_htmx import make_response
from wtforms import StringField
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import FileType

from .... import logger, db  # noqa F401
from ....tools import SpreadSheetColumn
from ...HTMXFlaskForm import HTMXFlaskForm


class RNAPrepForm(HTMXFlaskForm):
    _template_path = "workflows/library_prep/rna.html"

    columns = {
        "sample_name": SpreadSheetColumn("A", "sample_name", "Sample Name", "text", 170, str),
        "well": SpreadSheetColumn("B", "well", "Well", "text", 50, str),
        "qubit_concentration": SpreadSheetColumn("C", "qubit_concentration", "Qubit Concentration", "numeric", 100, float),
        "diluted_qubit_concentration": SpreadSheetColumn("D", "diluted_qubit_concentration", "Diluted Qubit Concentration", "numeric", 100, float),
        "ba_dilution": SpreadSheetColumn("E", "ba_dilution", "BA Dilution", "numeric", 100, float),
        "volume_ul": SpreadSheetColumn("F", "volume_ul", "Volume (µl)", "numeric", 100, float),
        "rin": SpreadSheetColumn("G", "rin", "RIN", "numeric", 100, float),
        "rna_total_ng": SpreadSheetColumn("H", "rna_total_ng", "RNA Total (ng)", "numeric", 100, float),
        "volume_h20_ul": SpreadSheetColumn("I", "volume_h20_ul", "Volume H2O (µl)", "numeric", 100, float),
        "volume_rna_ul": SpreadSheetColumn("J", "volume_rna_ul", "Volume RNA (µl)", "numeric", 100, float),
        "input_ng": SpreadSheetColumn("K", "input_ng", "Input (ng)", "numeric", 100, float),
        "index_1": SpreadSheetColumn("L", "index_1", "Index 1 (i7)", "text", 100, str),
        "index_2": SpreadSheetColumn("M", "index_2", "Index 2 (i5)", "text", 100, str),
        "pcr_cycles": SpreadSheetColumn("N", "pcr_cycles", "PCR Cycles", "numeric", 100, int),
        "qubit_after_2nd_cleanup": SpreadSheetColumn("O", "qubit_after_2nd_cleanup", "Qubit After 2nd Cleanup", "numeric", 100, float),
        "avg_fragment_size": SpreadSheetColumn("P", "avg_fragment_size", "Avg Fragment Size", "numeric", 100, int),
        "comment": SpreadSheetColumn("Q", "comment", "Comment", "text", 500, str),
    }

    colors = {
        "missing_value": "#FAD7A0",
        "invalid_value": "#F5B7B1",
        "duplicate_value": "#D7BDE2",
        "invalid_input": "#AED6F1"
    }

    spreadsheet_dummy = StringField(validators=[OptionalValidator()])

    def __init__(self, pool: models.Pool, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.pool = pool

        self._context["columns"] = RNAPrepForm.columns.values()
        self._context["pool"] = pool
        self._context["colors"] = RNAPrepForm.colors
        self.spreadsheet_style = dict()
        self._context["spreadsheet_style"] = self.spreadsheet_style

    def prepare(self):
        prep_table = self.get_table()
        self._context["spreadsheet_data"] = prep_table.replace(np.nan, "").values.tolist()

    def get_table(self) -> pd.DataFrame:
        if self.pool.prep_file is not None:
            prep_table = pd.read_csv(os.path.join(current_app.config["MEDIA_FOLDER"], self.pool.prep_file.path), sep="\t")
        else:
            if current_app.static_folder is None:
                raise ValueError("Static folder not set")
            prep_table = pd.read_csv(os.path.join(current_app.static_folder, "resources", "templates", "rna-prep.csv"), sep="\t")
            prep_table = prep_table[RNAPrepForm.columns.keys()]
            prep_table["sample_name"] = prep_table["sample_name"].astype(str).replace("nan", None)

        for library in self.pool.libraries:
            if library.name not in prep_table["sample_name"].values:
                prep_table.loc[prep_table[prep_table["sample_name"].isna()].index[0], "sample_name"] = library.name

        return prep_table
    
    def validate(self) -> bool:
        data = json.loads(self.formdata["spreadsheet"])  # type: ignore
        try:
            df = pd.DataFrame(data)
        except ValueError as e:
            self.spreadsheet_dummy.errors = (str(e),)
            return False
        
        columns = list(RNAPrepForm.columns.keys())
        if len(df.columns) != len(columns):
            self.spreadsheet_dummy.errors = (f"Invalid number of columns (expected {len(columns)}). Do not insert new columns or rearrange existing columns.",)
            return False
        
        df.columns = columns
        df = df.replace(r'^\s*$', None, regex=True)
        df = df.dropna(how="all")

        for library in self.pool.libraries:
            if library.name not in df["sample_name"].values:
                self.spreadsheet_dummy.errors = (f"Missing library: {library.name}",)
                return False
            
        self.df = df
            
        return True

    def process_request(self, user: models.User, action: Literal["save", "update"]) -> Response:
        if not self.validate():
            self.prepare()
            return self.make_response()
        
        if self.pool.prep_file is not None:
            path = os.path.join(current_app.config["MEDIA_FOLDER"], self.pool.prep_file.path)
            self.df.to_csv(path, sep="\t", index=False)
            size_bytes = os.path.getsize(path)
            self.pool.prep_file.size_bytes = size_bytes
            self.pool.prep_file.timestamp_utc = db.timestamp()
            self.pool = db.update_pool(self.pool)
        else:
            hash = str(uuid4())
            path = os.path.join(current_app.config["MEDIA_FOLDER"], FileType.RNA_PREP_TABLE.dir, f"{hash}.tsv")
            self.df.to_csv(path, sep="\t", index=False)
            size_bytes = os.path.getsize(path)
            
            db_file = db.create_file(
                name=f"{self.pool.name}-prep",
                type=FileType.RNA_PREP_TABLE,
                extension=".tsv",
                uploader_id=user.id,
                size_bytes=size_bytes,
                uuid=hash
            )

            self.pool.prep_file_id = db_file.id
            self.pool = db.update_pool(self.pool)

        if action == "save":
            flash("RNA Prep table saved!", "success")
            return make_response(redirect=url_for("pools_page.pool_page", pool_id=self.pool.id))
        else:
            self.prepare()
            return self.make_response()


        
