import pandas as pd

from flask import Response

from opengsync_db import models
from opengsync_db.categories import FeatureType, MUXType, LibraryType, ServiceType, LibraryTypeEnum, SubmissionType

from .... import logger, db
from ..common.CommonOligoMuxForm import CommonOligoMuxForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .CompleteSASForm import CompleteSASForm
from .PooledLibraryAnnotationForm import PooledLibraryAnnotationForm
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm
from .ParseMuxAnnotationForm import ParseMuxAnnotationForm
from .OCMAnnotationForm import OCMAnnotationForm


class OligoMuxAnnotationForm(CommonOligoMuxForm):
    _template_path = "workflows/library_annotation/sas-oligo_mux_annotation.html"
    _workflow_name = "library_annotation"
    seq_request: models.SeqRequest

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        CommonOligoMuxForm.__init__(
            self,
            seq_request=seq_request, lab_prep=None, library=None,
            workflow=OligoMuxAnnotationForm._workflow_name,
            uuid=uuid, formdata=formdata,
            additional_columns=[]
        )

    def fill_previous_form(self):
        mux_table = CommonOligoMuxForm.get_mux_table(self.tables["sample_pooling_table"])
        self.spreadsheet.set_data(mux_table)
    
    def process_request(self) -> Response:
        if not self.validate():
            self._context["kits"] = self.kits
            return self.make_response()
    
        sample_pooling_table = self.tables["sample_pooling_table"]

        sample_pooling_table["mux_barcode"] = None
        sample_pooling_table["mux_pattern"] = None
        sample_pooling_table["mux_read"] = None
        sample_pooling_table["mux_kit"] = None
        sample_pooling_table["mux_feature"] = None

        for _, row in self.df.iterrows():
            sample_name = row["sample_name"]
            sample_pool = row["sample_pool"]
            sample_pooling_table.loc[(sample_pooling_table["sample_name"] == sample_name) & (sample_pooling_table["sample_pool"] == sample_pool), "mux_barcode"] = row["barcode"]
            sample_pooling_table.loc[(sample_pooling_table["sample_name"] == sample_name) & (sample_pooling_table["sample_pool"] == sample_pool), "mux_pattern"] = row["pattern"]
            sample_pooling_table.loc[(sample_pooling_table["sample_name"] == sample_name) & (sample_pooling_table["sample_pool"] == sample_pool), "mux_read"] = row["read"]
            sample_pooling_table.loc[(sample_pooling_table["sample_name"] == sample_name) & (sample_pooling_table["sample_pool"] == sample_pool), "mux_kit"] = row["kit"]
            sample_pooling_table.loc[(sample_pooling_table["sample_name"] == sample_name) & (sample_pooling_table["sample_pool"] == sample_pool), "mux_feature"] = row["feature"]

        if OligoMuxAnnotationForm.is_abc_hashed(self):
            sample_pooling_table["mux_type_id"] = MUXType.TENX_ABC_HASH.id
        else:
            sample_pooling_table["mux_type_id"] = MUXType.TENX_OLIGO.id

        library_table_data = {
            "library_name": [],
            "sample_name": [],
            "library_type": [],
            "library_type_id": [],
        }

        service_type_enum = ServiceType.get(self.metadata["service_type_id"])

        def add_library(sample_pool: str, library_type: LibraryTypeEnum):
            library_table_data["library_name"].append(f"{sample_pool}_{library_type.identifier}")
            library_table_data["sample_name"].append(sample_pool)
            library_table_data["library_type"].append(library_type.name)
            library_table_data["library_type_id"].append(library_type.id)

        for (sample_pool,), _ in sample_pooling_table.groupby(["sample_pool"], sort=False):
            for library_type in service_type_enum.library_types:
                add_library(sample_pool, library_type)

            if self.metadata["antibody_capture"]:
                if service_type_enum in [ServiceType.TENX_SC_SINGLE_PLEX_FLEX, ServiceType.TENX_SC_4_PLEX_FLEX, ServiceType.TENX_SC_16_PLEX_FLEX]:
                    add_library(sample_pool, LibraryType.TENX_SC_ABC_FLEX)
                else:
                    add_library(sample_pool, LibraryType.TENX_ANTIBODY_CAPTURE)

            if self.metadata["vdj_b"]:
                add_library(sample_pool, LibraryType.TENX_VDJ_B)

            if self.metadata["vdj_t"]:
                add_library(sample_pool, LibraryType.TENX_VDJ_T)

            if self.metadata["vdj_t_gd"]:
                add_library(sample_pool, LibraryType.TENX_VDJ_T_GD)

            if self.metadata["crispr_screening"]:
                add_library(sample_pool, LibraryType.TENX_CRISPR_SCREENING)

        library_table = pd.DataFrame(library_table_data)
        library_table["seq_depth"] = None
                
        kit_table = self.df[self.df["kit"].notna()][["kit"]].drop_duplicates().copy()
        kit_table["type_id"] = FeatureType.CMO.id
        kit_table["kit_id"] = None

        if kit_table.shape[0] > 0:
            if (existing_kit_table := self.tables.get("kit_table")) is None:  # type: ignore
                self.tables["kit_table"] = kit_table
            else:
                kit_table = pd.concat([kit_table[kit_table["type_id"] != FeatureType.CMO.id], existing_kit_table])
                self.tables["kit_table"] = kit_table
        
        self.tables["sample_pooling_table"] = sample_pooling_table
        self.step()

        if self.seq_request.submission_type.id == SubmissionType.POOLED_LIBRARIES.id:
            next_form = PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OCMAnnotationForm.is_applicable(self):
            next_form = OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif ParseMuxAnnotationForm.is_applicable(self):
            next_form = ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FeatureAnnotationForm.is_applicable(self):
            next_form = FeatureAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OpenSTAnnotationForm.is_applicable(self):
            next_form = OpenSTAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif VisiumAnnotationForm.is_applicable(self):
            next_form = VisiumAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif ParseCRISPRGuideAnnotationForm.is_applicable(self):
            next_form = ParseCRISPRGuideAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        else:
            next_form = CompleteSASForm(seq_request=self.seq_request, uuid=self.uuid)

        return next_form.make_response()