import pandas as pd

from flask import Response

from opengsync_db import models
from opengsync_db.categories import LibraryType, SubmissionType, LibraryTypeEnum, SubmissionType
from opengsync_server.forms.MultiStepForm import StepFile

from .... import logger, db
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn
from ...MultiStepForm import MultiStepForm
from ..common import CommonFlexMuxForm
from .CompleteSASForm import CompleteSASForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .PooledLibraryAnnotationForm import PooledLibraryAnnotationForm
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm
from .ParseMuxAnnotationForm import ParseMuxAnnotationForm

class FlexAnnotationForm(CommonFlexMuxForm):
    _template_path = "workflows/library_annotation/sas-flex_annotation.html"
    _workflow_name = "library_annotation"
    seq_request: models.SeqRequest

    columns: list = [
        TextColumn("sample_name", "Demultiplexed Name", 300, required=True, read_only=True),
        TextColumn("sample_pool", "Sample Pool Name", 300, required=True, read_only=True),
        TextColumn("barcode_id", "Bardcode ID", 200, required=False, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH, clean_up_fnc=CommonFlexMuxForm.padded_barcode_id),
    ]

    @staticmethod
    def is_applicable(current_step: MultiStepForm, seq_request: models.SeqRequest) -> bool:
        return (
            seq_request.submission_type in [SubmissionType.POOLED_LIBRARIES, SubmissionType.UNPOOLED_LIBRARIES] and
            LibraryType.TENX_SC_GEX_FLEX.id in current_step.tables["library_table"]["library_type_id"].values
        )

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        CommonFlexMuxForm.__init__(
            self, uuid=uuid, formdata=formdata, workflow=FlexAnnotationForm._workflow_name,
            seq_request=seq_request, library=None, lab_prep=None, columns=FlexAnnotationForm.columns
        )

    def fill_previous_form(self, previous_form: StepFile):
        mux_table = previous_form.tables["sample_pooling_table"]
        mux_table["barcode_id"] = mux_table["mux_barcode"]
        self.spreadsheet.set_data(mux_table)
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        sample_pooling_table = self.tables["sample_pooling_table"]
        
        if self.flex_table is None:
            logger.error(f"{self.uuid}: Flex table is None.")
            raise Exception("Flex table is None.")
        
        sample_pooling_table["mux_barcode"] = utils.map_columns(sample_pooling_table, self.df, idx_columns=["sample_name", "sample_pool"], col="barcode_id")

        self.update_table("sample_pooling_table", sample_pooling_table, update_data=False)

        library_table_data = {
            "library_name": [],
            "sample_name": [],
            "library_type": [],
            "library_type_id": [],
        }

        def add_library(sample_pool: str, library_type: LibraryTypeEnum):
            library_table_data["library_name"].append(f"{sample_pool}_{library_type.identifier}")
            library_table_data["sample_name"].append(sample_pool)
            library_table_data["library_type"].append(library_type.name)
            library_table_data["library_type_id"].append(library_type.id)

        for (sample_pool,), _ in sample_pooling_table.groupby(["sample_pool"], sort=False):
            add_library(sample_pool, LibraryType.TENX_SC_GEX_FLEX)

            if self.metadata["antibody_capture"]:
                add_library(sample_pool, LibraryType.TENX_SC_ABC_FLEX)

        library_table = pd.DataFrame(library_table_data)
        library_table["seq_depth"] = None
        self.update_table("library_table", library_table)
                        
        if self.metadata["submission_type_id"] == SubmissionType.POOLED_LIBRARIES.id:
            next_form = PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
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
    