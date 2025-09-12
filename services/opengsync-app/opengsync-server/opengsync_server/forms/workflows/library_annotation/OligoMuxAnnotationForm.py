import pandas as pd

from flask import Response

from opengsync_db import models
from opengsync_db.categories import FeatureType, MUXType

from .... import logger, db  # noqa
from ..common.CommonOligoMuxForm import CommonOligoMuxForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .SampleAttributeAnnotationForm import SampleAttributeAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm


class OligoMuxAnnotationForm(CommonOligoMuxForm):
    _template_path = "workflows/library_annotation/sas-oligo_mux_annotation.html"
    _workflow_name = "library_annotation"
    seq_request: models.SeqRequest

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        CommonOligoMuxForm.__init__(
            self,
            seq_request=seq_request, lab_prep=None,
            workflow=OligoMuxAnnotationForm._workflow_name,
            uuid=uuid, formdata=formdata,
            additional_columns=[]
        )
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        sample_table = self.tables["sample_table"]
        sample_pooling_table = self.tables["sample_pooling_table"]

        sample_data = {"sample_name": []}

        pooling_data = {
            "sample_name": [],
            "library_name": [],
            "mux_barcode": [],
            "mux_pattern": [],
            "mux_read": [],
            "kit": [],
            "feature": [],
            "mux_type_id": [],
            "sample_pool": [],
        }

        for _, mux_row in self.df.iterrows():
            sample_data["sample_name"].append(mux_row["demux_name"])
            for _, pooling_row in sample_pooling_table[sample_pooling_table["sample_name"] == mux_row["sample_name"]].iterrows():
                pooling_data["sample_name"].append(mux_row["demux_name"])
                pooling_data["library_name"].append(pooling_row["library_name"])
                pooling_data["mux_barcode"].append(mux_row["sequence"])
                pooling_data["mux_pattern"].append(mux_row["pattern"])
                pooling_data["mux_read"].append(mux_row["read"])
                pooling_data["kit"].append(mux_row["kit"])
                pooling_data["feature"].append(mux_row["feature"])
                pooling_data["mux_type_id"].append(MUXType.TENX_OLIGO.id)
                pooling_data["sample_pool"].append(mux_row["sample_name"])
        
        sample_pooling_table = pd.DataFrame(pooling_data)
        self.update_table("sample_pooling_table", sample_pooling_table, update_data=False)

        sample_table = pd.DataFrame(sample_data)
        sample_table = sample_table.drop_duplicates().reset_index(drop=True)
        sample_table["sample_id"] = None
        if (project_id := self.metadata.get("project_id")) is not None:
            if (project := db.projects.get(project_id)) is None:
                logger.error(f"{self.uuid}: Project with ID {self.metadata['project_id']} does not exist.")
                raise ValueError(f"Project with ID {self.metadata['project_id']} does not exist.")
            
            for sample in project.samples:
                sample_table.loc[sample_table["sample_name"] == sample.name, "sample_id"] = sample.id

        self.update_table("sample_table", sample_table, update_data=False)
                
        kit_table = self.df[self.df["kit"].notna()][["kit"]].drop_duplicates().copy()
        kit_table["type_id"] = FeatureType.CMO.id
        kit_table["kit_id"] = None

        if kit_table.shape[0] > 0:
            if (existing_kit_table := self.tables.get("kit_table")) is None:  # type: ignore
                self.add_table("kit_table", kit_table)
            else:
                kit_table = pd.concat([kit_table[kit_table["type_id"] != FeatureType.CMO.id], existing_kit_table])
                self.update_table("kit_table", kit_table, update_data=False)
        
        self.update_data()

        if FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = SampleAttributeAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)

        return next_form.make_response()