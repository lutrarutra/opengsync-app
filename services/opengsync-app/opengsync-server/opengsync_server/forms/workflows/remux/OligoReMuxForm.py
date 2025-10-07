from typing import Optional

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import BooleanField

from opengsync_db import models
from opengsync_db.categories import MUXType

from .... import logger, db, tools
from ....tools import utils, StaticSpreadSheet  # noqa F401
from ....tools.spread_sheet_components import TextColumn
from ..common.CommonOligoMuxForm import CommonOligoMuxForm


class OligoReMuxForm(CommonOligoMuxForm):
    _template_path = "workflows/library_remux/oligo_annotation.html"
    _workflow_name = "library_remux"
    library: models.Library

    apply_to_sample_pool = BooleanField("Apply to all samples in pool", description="Will copy and apply the changes to all other sample-links in sample-pool. If you don't know what you are doing, leave it as is.", default=True)

    mux_type = MUXType.TENX_OLIGO
    
    def __init__(self, library: models.Library, formdata: dict | None = None, uuid: Optional[str] = None):
        CommonOligoMuxForm.__init__(
            self,
            library=library, seq_request=None, lab_prep=None,
            uuid=uuid, formdata=formdata, workflow=OligoReMuxForm._workflow_name,
            additional_columns=[]
        )
        self.library_sample_pool_table = db.pd.get_library_sample_pool(self.library.id, expand_mux=True).sort_values(
            by=["sample_name", "library_name", "sample_pool"]
        )
        self._context["library_sample_pool_table"] = StaticSpreadSheet(df=self.library_sample_pool_table, columns=[
            TextColumn("sample_name", "Demultiplexed Name", 170),
            TextColumn("sample_pool", "Sample Pool Name", 170),
            TextColumn("library_name", "Library Name", 170),
            TextColumn("barcode", "Sequence", 150),
            TextColumn("pattern", "Pattern", 200),
            TextColumn("read", "Read", 100),
        ])

    def prepare(self):
        self.apply_to_sample_pool.data = self.library_sample_pool_table.duplicated(
            ["sample_name", "barcode", "pattern", "read"], keep=False
        ).all()

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        self.df["mux_read"] = self.df["read"]
        self.df["mux_barcode"] = self.df["barcode"]
        self.df["mux_pattern"] = self.df["pattern"]

        self.pooling_table["mux_read"] = utils.map_columns(self.pooling_table, self.df, ["sample_name", "sample_pool"], "mux_read")
        self.pooling_table["mux_barcode"] = utils.map_columns(self.pooling_table, self.df, ["sample_name", "sample_pool"], "mux_barcode")
        self.pooling_table["mux_pattern"] = utils.map_columns(self.pooling_table, self.df, ["sample_name", "sample_pool"], "mux_pattern")

        if not self.apply_to_sample_pool.data:
            for _, row in self.pooling_table.iterrows():
                sample_id = int(row["sample_id"])

                if (link := db.links.get_sample_library_link(sample_id=sample_id, library_id=self.library.id)) is None:
                    logger.error(f"Could not find link for sample {sample_id} and library {self.library.id}")
                    raise Exception("Internal error")
                
                if link.mux is None:
                    link.mux = {}

                link.mux["barcode"] = row["mux_barcode"]
                link.mux["read"] = row["mux_read"]
                link.mux["pattern"] = row["mux_pattern"]

                db.links.update_sample_library_link(link)
        else:
            for _, row in self.df.iterrows():
                for _, pool_row in self.library_sample_pool_table[
                    self.library_sample_pool_table["sample_name"] == row["sample_name"]
                ].iterrows():
                    sample_id = int(pool_row["sample_id"])
                    library_id = int(pool_row["library_id"])

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
        return make_response(redirect=(url_for("libraries_page.library", library_id=self.library.id)))
        
