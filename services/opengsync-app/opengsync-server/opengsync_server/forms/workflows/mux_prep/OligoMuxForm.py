from typing import Optional

import pandas as pd

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import FormField

from opengsync_db import models
from opengsync_db.categories import LibraryStatus, MUXType

from .... import logger, tools, db  # noqa F401
from ..common.CommonOligoMuxForm import CommonOligoMuxForm
from ....tools.spread_sheet_components import InvalidCellValue, MissingCellValue, DuplicateCellValue
from ...SearchBar import OptionalSearchBar
from ...SpreadsheetInput import SpreadsheetInput


class OligoMuxForm(CommonOligoMuxForm):
    _template_path = "workflows/mux_prep/mux_prep-oligo_mux_annotation.html"
    _workflow_name = "mux_prep"
    lab_prep: models.LabPrep

    mux_type = MUXType.TENX_OLIGO
    
    def __init__(self, lab_prep: models.LabPrep, formdata: dict | None = None, uuid: Optional[str] = None):
        CommonOligoMuxForm.__init__(
            self,
            lab_prep=lab_prep, seq_request=None,
            uuid=uuid, formdata=formdata, workflow=OligoMuxForm._workflow_name,
            additional_columns=[]
        )

        self.sample_table = db.pd.get_lab_prep_samples(lab_prep.id)
        self.sample_table = self.sample_table[self.sample_table["mux_type"].isin([MUXType.TENX_OLIGO])]
        self.mux_table = self.sample_table.drop_duplicates(subset=["sample_name", "sample_pool"], keep="first")

    def __get_template(self) -> pd.DataFrame:
        template_data = {
            "demux_name": [],
            "sample_pool": [],
            "kit": [],
            "feature": [],
            "sequence": [],
            "pattern": [],
            "read": [],
        }

        for _, row in self.mux_table.iterrows():
            template_data["sample_pool"].append(row["sample_pool"])
            template_data["demux_name"].append(row["sample_name"])
            template_data["kit"].append(None)
            template_data["feature"].append(None)
            if (mux := row.get("mux")) is None:
                template_data["sequence"].append(None)
                template_data["pattern"].append(None)
                template_data["read"].append(None)
            else:
                template_data["sequence"].append(mux.get("barcode"))
                template_data["pattern"].append(mux.get("pattern"))
                template_data["read"].append(mux.get("read"))

        return pd.DataFrame(template_data)

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        sample_pool_map = self.df.set_index("demux_name")["sample_pool"].to_dict()
        sequence_map = self.df.set_index("demux_name")["sequence"].to_dict()
        pattern_map = self.df.set_index("demux_name")["pattern"].to_dict()
        read_map = self.df.set_index("demux_name")["read"].to_dict()
        
        self.sample_table["new_sample_pool"] = self.sample_table["sample_name"].apply(lambda x: sample_pool_map[x])
        self.sample_table["mux_barcode"] = self.sample_table["sample_name"].apply(lambda x: sequence_map[x])
        self.sample_table["mux_pattern"] = self.sample_table["sample_name"].apply(lambda x: pattern_map[x])
        self.sample_table["mux_read"] = self.sample_table["sample_name"].apply(lambda x: read_map[x])
        self.sample_table["mux_type_id"] = MUXType.TENX_OLIGO.id
                
        libraries: dict[str, models.Library] = dict()
        old_libraries: list[int] = []
        
        for _, row in self.sample_table.iterrows():
            if (old_library := db.libraries.get(int(row["library_id"]))) is None:
                logger.error(f"Library {row['library_id']} not found.")
                raise Exception(f"Library {row['library_id']} not found.")
            
            if old_library.id not in old_libraries:
                old_libraries.append(old_library.id)
            
            if (sample := db.samples.get(int(row["sample_id"]))) is None:
                logger.error(f"Sample {row['sample_id']} not found.")
                raise Exception(f"Sample {row['sample_id']} not found.")
            
            lib = f"{row['new_sample_pool']}_{old_library.type.identifier}"
            if lib not in libraries.keys():
                new_library = db.libraries.create(
                    name=lib,
                    sample_name=row["new_sample_pool"],
                    library_type=old_library.type,
                    status=LibraryStatus.PREPARING,
                    owner_id=old_library.owner_id,
                    seq_request_id=old_library.seq_request_id,
                    lab_prep_id=self.lab_prep.id,
                    genome_ref=old_library.genome_ref,
                    assay_type=old_library.assay_type,
                    mux_type=old_library.mux_type,
                    nuclei_isolation=old_library.nuclei_isolation,
                )
                libraries[lib] = new_library
            else:
                new_library = libraries[lib]

            db.links.link_sample_library(
                sample_id=sample.id, library_id=new_library.id,
                mux={
                    "barcode": row["mux_barcode"],
                    "pattern": row["mux_pattern"],
                    "read": row["mux_read"],
                },
            )
            new_library.features = old_library.features
            db.libraries.update(new_library)

        for old_library_id in old_libraries:
            if (old_library := db.libraries.get(old_library_id)) is None:
                continue
            db.libraries.delete(old_library, delete_orphan_samples=False)

        flash("Changes saved!", "success")
        return make_response(redirect=(url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id)))