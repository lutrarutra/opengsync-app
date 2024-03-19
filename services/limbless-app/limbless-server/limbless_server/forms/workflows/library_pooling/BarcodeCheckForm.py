from typing import Optional
from flask import Response
import pandas as pd

from wtforms import BooleanField
from flask import url_for, flash
from flask_htmx import make_response

from limbless_db import models

from .... import db, logger
from ...TableDataForm import TableDataForm
from ...HTMXFlaskForm import HTMXFlaskForm


class BarcodeCheckForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/library_pooling/pooling-4.html"
    _form_label = "barcode_check_form"

    reverse_complement_index_1 = BooleanField("Reverse complement index 1", default=False)
    reverse_complement_index_2 = BooleanField("Reverse complement index 2", default=False)
    reverse_complement_index_3 = BooleanField("Reverse complement index 3", default=False)
    reverse_complement_index_4 = BooleanField("Reverse complement index 4", default=False)

    def __init__(self, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, uuid=uuid)
    
    def prepare(self, data: Optional[dict[str, pd.DataFrame]] = None) -> dict:
        if data is None:
            data = self.get_data()

        data = self.get_data()
        df = self.get_data()["pooling_table"]

        indices_present = []
        if "index_1" in df.columns:
            indices_present.append("index_1")
        if "index_2" in df.columns:
            indices_present.append("index_2")
        if "index_3" in df.columns:
            indices_present.append("index_3")
        if "index_4" in df.columns:
            indices_present.append("index_4")
        
        reused_barcodes = (df[indices_present].duplicated(keep=False)) & (~df[indices_present].isna().all(axis=1))

        libraries_data = []

        for i, row in df.iterrows():
            library_id = row["id"]
            library = db.get_library(library_id)

            _data = {
                "library": library,
                "error": None,
                "warning": "",
                "info": "",
            }
            if "index_1" in row:
                _data["index_1"] = row["index_1"]
            
            if "index_2" in row:
                _data["index_2"] = row["index_2"]

            if "index_3" in row:
                _data["index_3"] = row["index_3"]

            if "index_4" in row:
                _data["index_4"] = row["index_4"]

            if "adapter" in row:
                _data["adapter"] = row["adapter"]

            if reused_barcodes.at[i]:
                _data["warning"] += "Index combination is reused in two or more libraries. "

            libraries_data.append(_data)

        data["pooling_table"] = df
        self.update_data(data)

        return {
            "libraries_data": libraries_data,
            "show_index_1": "index_1" in df.columns,
            "show_index_2": "index_2" in df.columns,
            "show_index_3": "index_3" in df.columns,
            "show_index_4": "index_4" in df.columns,
        }
    
    def __parse(self, user: models.User) -> dict[str, pd.DataFrame]:
        data = self.get_data()

        pooling_table = data["pooling_table"]

        for _, row in pooling_table.iterrows():
            library = db.get_library(row["id"])
            library.index_1_sequence = row["index_1"] if not pd.isna(row["index_1"]) else None
            library.index_2_sequence = row["index_2"] if not pd.isna(row["index_2"]) else None
            library.index_3_sequence = row["index_3"] if not pd.isna(row["index_3"]) else None
            library.index_4_sequence = row["index_4"] if not pd.isna(row["index_4"]) else None
            library.adapter = row["adapter"] if not pd.isna(row["adapter"]) else None
            library = db.update_library(library)

        n_pools = 0
        for pool_label, _df in pooling_table.groupby("pool"):
            pool_label = str(pool_label)
            pool = db.create_pool(
                name=pool_label,
                owner_id=user.id,
                contact_name=_df["contact_person_name"].iloc[0],
                contact_email=_df["contact_person_email"].iloc[0],
                contact_phone=_df["contact_person_phone"].iloc[0],
            )

            for _, row in _df.iterrows():
                library_id = row["id"]
                db.link_library_pool(
                    library_id=library_id, pool_id=pool.id
                )

            n_pools += 1

        flash(f"Created and indexed {n_pools} succefully.", "success")
        logger.debug(f"Created and indexed {n_pools} succefully.")
        return data
    
    def process_request(self, **context) -> Response:
        validated = self.validate()
        if not validated:
            return self.make_response(**context)
        
        experiment: models.Experiment = context["experiment"]
        user: models.User = context["user"]
        self.__parse(user)
        
        return make_response(
            redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id)
        )