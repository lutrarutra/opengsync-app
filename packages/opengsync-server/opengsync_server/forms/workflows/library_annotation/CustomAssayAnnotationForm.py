import pandas as pd

from flask import Response, url_for

from opengsync_db import models
from opengsync_db.categories import LibraryType, MUXType, LibraryTypeEnum

from .... import logger, db
from ....tools.spread_sheet_components import InvalidCellValue, DuplicateCellValue, DropdownColumn, CategoricalDropDown
from ...MultiStepForm import MultiStepForm
from ...SpreadsheetInput import SpreadsheetInput
from .OligoMuxAnnotationForm import OligoMuxAnnotationForm
from .VisiumAnnotationForm import VisiumAnnotationForm
from .FlexAnnotationForm import FlexAnnotationForm
from .CompleteSASForm import CompleteSASForm
from .FeatureAnnotationForm import FeatureAnnotationForm
from .OCMAnnotationForm import OCMAnnotationForm
from .OpenSTAnnotationForm import OpenSTAnnotationForm
from .PooledLibraryAnnotationForm import PooledLibraryAnnotationForm
from .ParseCRISPRGuideAnnotationForm import ParseCRISPRGuideAnnotationForm
from .ParseMuxAnnotationForm import ParseMuxAnnotationForm


class CustomAssayAnnotationFrom(MultiStepForm):
    _template_path = "workflows/library_annotation/sas-custom_assay_annotation.html"
    _workflow_name = "library_annotation"
    _step_name = "custom_assay_annotation"

    def __init__(self, seq_request: models.SeqRequest, uuid: str, formdata: dict | None = None):
        MultiStepForm.__init__(
            self, uuid=uuid, workflow=CustomAssayAnnotationFrom._workflow_name,
            step_name=CustomAssayAnnotationFrom._step_name,
            formdata=formdata, step_args={}
        )
        self.seq_request = seq_request
        self._context["seq_request"] = seq_request
        self.sample_pooling_table = self.tables["sample_pooling_table"]
        self.sample_pools = self.sample_pooling_table["sample_pool"].unique().tolist()

        self.columns = [
            DropdownColumn("sample_pool", "Sample Name (Pool)", 300, required=True, choices=self.sample_pools),
            CategoricalDropDown("library_type_id", "Library Type", 300, categories=dict(LibraryType.as_selectable()), required=True),
        ]

        self.spreadsheet: SpreadsheetInput = SpreadsheetInput(
            columns=self.columns, csrf_token=self._csrf_token,
            post_url=url_for('library_annotation_workflow.parse_custom_assay_annotation_form', seq_request_id=seq_request.id, uuid=self.uuid),
            formdata=formdata, allow_new_rows=True, df=self.sample_pooling_table.drop_duplicates(subset=["sample_pool"])
        )
        self.mux_type = MUXType.get(self.metadata["mux_type_id"]) if self.metadata.get("mux_type_id") is not None else None

    def fill_previous_form(self):
        df = self.tables["library_table"].rename(columns={"sample_name": "sample_pool"})
        df = df[["sample_pool", "library_type_id"]].drop_duplicates()
        self.spreadsheet.set_data(df)

    def validate(self) -> bool:
        if not super().validate():
            return False

        if not self.spreadsheet.validate():
            return False
    
        df = self.spreadsheet.df
        
        for sample_pool in self.sample_pools:
            if sample_pool not in df["sample_pool"].values:
                self.spreadsheet.add_general_error(f"No library type(s) specified for '{sample_pool}'")           
            
        duplicated = df.duplicated(subset=["sample_pool", "library_type_id"], keep=False)
        df["library_type"] = df["library_type_id"].map(LibraryType.get)
        for idx, row in df.iterrows():
            library_type: LibraryTypeEnum = row["library_type"]
            if duplicated.at[idx]:
                self.spreadsheet.add_error(idx, "library_type_id", DuplicateCellValue(f"Library type '{library_type.name}' is duplicated for sample pool '{row['sample_pool']}'"))

            if library_type == LibraryType.TENX_MUX_OLIGO and self.mux_type != MUXType.TENX_OLIGO:
                self.spreadsheet.add_error(idx, "library_type_id", InvalidCellValue(f"Library type '{library_type.name}' is incompatible with the selected multiplexing method '{self.mux_type.name if self.mux_type else 'N/A'}'"))

        self.df = df
        return len(self.spreadsheet._errors) == 0

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()

        library_table_data = {
            "library_name": [],
            "sample_name": [],
            "library_type": [],
            "library_type_id": [],
        }

        sample_pooling_table = {
            "sample_name": [],
            "library_name": [],
            "sample_pool": [],
        }

        def add_library(sample_pool: str, library_type: LibraryTypeEnum):
            library_name = f"{sample_pool}_{library_type.identifier}"
            
            library_table_data["library_name"].append(library_name)
            library_table_data["sample_name"].append(sample_pool)
            library_table_data["library_type"].append(library_type.name)
            library_table_data["library_type_id"].append(library_type.id)
            return library_name

        for (sample_pool, sample_name), _df in self.sample_pooling_table.groupby(["sample_pool", "sample_name"], sort=False):
            for _, row in self.df.loc[self.df["sample_pool"] == sample_pool].iterrows():
                library_name = add_library(sample_pool, row["library_type"])

                sample_pooling_table["sample_name"].append(sample_name)
                sample_pooling_table["library_name"].append(library_name)
                sample_pooling_table["sample_pool"].append(sample_pool)

        library_table = pd.DataFrame(library_table_data)
        self.sample_pooling_table = pd.DataFrame(sample_pooling_table)
        self.sample_pooling_table["mux_type_id"] = self.mux_type.id if self.mux_type else None
        self.sample_pooling_table["mux_barcode"] = None

        self.tables["library_table"] = library_table
        self.tables["sample_pooling_table"] = self.sample_pooling_table
        self.step()

        if OCMAnnotationForm.is_applicable(self):
            next_form = OCMAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif OligoMuxAnnotationForm.is_applicable(self):
            next_form = OligoMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif FlexAnnotationForm.is_applicable(self, seq_request=self.seq_request):
            next_form = FlexAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif ParseMuxAnnotationForm.is_applicable(self):
            next_form = ParseMuxAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
        elif PooledLibraryAnnotationForm.is_applicable(self):
            next_form = PooledLibraryAnnotationForm(seq_request=self.seq_request, uuid=self.uuid)
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

        