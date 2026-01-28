from typing import Optional

from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models
from opengsync_db.categories import MUXType

from .... import logger, db
from ....tools import utils
from ..common.CommonOligoMuxForm import CommonOligoMuxForm


class OligoMuxForm(CommonOligoMuxForm):
    _template_path = "workflows/mux_prep/mux_prep-oligo_mux_annotation.html"
    _workflow_name = "mux_prep"
    lab_prep: models.LabPrep

    mux_type = MUXType.TENX_OLIGO
    
    def __init__(self, lab_prep: models.LabPrep, formdata: dict | None = None, uuid: str | None = None):
        CommonOligoMuxForm.__init__(
            self,
            lab_prep=lab_prep, seq_request=None, library=None,
            uuid=uuid, formdata=formdata, workflow=OligoMuxForm._workflow_name,
            additional_columns=[]
        )

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        self.df["mux_read"] = self.df["read"]
        self.df["mux_barcode"] = self.df["barcode"]
        self.df["mux_pattern"] = self.df["pattern"]

        self.pooling_table["mux_read"] = utils.map_columns(self.pooling_table, self.df, ["sample_name", "sample_pool"], "mux_read")
        self.pooling_table["mux_barcode"] = utils.map_columns(self.pooling_table, self.df, ["sample_name", "sample_pool"], "mux_barcode")
        self.pooling_table["mux_pattern"] = utils.map_columns(self.pooling_table, self.df, ["sample_name", "sample_pool"], "mux_pattern")
        
        for _, row in self.pooling_table.iterrows():
            sample_id = int(row["sample_id"])
            library_id = int(row["library_id"])

            if (link := db.links.get_sample_library_link(sample_id=sample_id, library_id=library_id)) is None:
                logger.error(f"Could not find link for sample {sample_id} and library {library_id}")
                raise Exception("Internal error")
            
            if link.mux is None:
                link.mux = {}

            link.mux["barcode"] = row["mux_barcode"]
            link.mux["read"] = row["mux_read"]
            link.mux["pattern"] = row["mux_pattern"]

            db.links.update_sample_library_link(link)

        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id)))