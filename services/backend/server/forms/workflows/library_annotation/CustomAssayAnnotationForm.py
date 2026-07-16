import pandas as pd
from fastapi import Depends, Response

from opengsync_db import categories as C

from ....components import inputs
from ....components.tables import DropdownColumn, CategoricalDropDown, DuplicateCellValue, InvalidCellValue
from ...HTMXForm import RouteFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep

class CustomAssayAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-custom_assay_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        DropdownColumn("sample_pool", "Sample Name (Pool)", 300, required=True, choices=[]),
        CategoricalDropDown("library_type_id", "Library Type", 300, categories=dict(C.LibraryType.as_selectable()), required=True),
    ])

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.sample_pooling_table = workflow.tables["sample_pooling_table"]
        self.sample_pools = self.sample_pooling_table["sample_pool"].unique().tolist()
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        self.spreadsheet.columns["sample_pool"].choices = self.sample_pools  # type: ignore
        self.spreadsheet.set_data(self.sample_pooling_table.drop_duplicates(subset=["sample_pool"]))
        self.mux_type = C.MUXType.get(workflow.metadata["mux_type_id"]) if workflow.metadata.get("mux_type_id") is not None else None

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: CustomAssayAnnotationForm = Depends(CustomAssayAnnotationForm.PreviousStep()),
        ) -> Response:
            df = form.workflow.tables["library_table"].rename(columns={"sample_name": "sample_pool"})
            df = df[["sample_pool", "library_type_id"]].drop_duplicates()
            form.spreadsheet.set_data(df)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: CustomAssayAnnotationForm = Depends(CustomAssayAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data
            form.workflow.tables["library_table"] = df.rename(columns={"sample_pool": "sample_name"})
            for sample_pool in form.sample_pools:
                if sample_pool not in df["sample_pool"].values:
                    form.spreadsheet.add_general_error(f"No library type(s) specified for '{sample_pool}'")           
                
            duplicated = df.duplicated(subset=["sample_pool", "library_type_id"], keep=False)
            df["library_type"] = df["library_type_id"].map(C.LibraryType.get)
            for idx, row in df.iterrows():
                library_type: C.LibraryType = row["library_type"]
                if duplicated.at[idx]:
                    form.spreadsheet.add_error(idx, "library_type_id", DuplicateCellValue(f"Library type '{library_type.name}' is duplicated for sample pool '{row['sample_pool']}'"))

                if library_type == C.LibraryType.TENX_MUX_OLIGO and form.mux_type != C.MUXType.TENX_OLIGO:
                    form.spreadsheet.add_error(idx, "library_type_id", InvalidCellValue(f"Library type '{library_type.name}' is incompatible with the selected multiplexing method '{form.mux_type.name if form.mux_type else 'N/A'}'"))

            form.assert_valid()
            
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

            def add_library(sample_pool: str, library_type: C.LibraryType):
                library_name = f"{sample_pool}_{library_type.identifier}"
                
                library_table_data["library_name"].append(library_name)
                library_table_data["sample_name"].append(sample_pool)
                library_table_data["library_type"].append(library_type.name)
                library_table_data["library_type_id"].append(library_type.id)
                return library_name

            for (sample_pool, sample_name), _df in form.sample_pooling_table.groupby(["sample_pool", "sample_name"], sort=False):
                for _, row in df.loc[df["sample_pool"] == sample_pool].iterrows():
                    library_name = add_library(sample_pool, C.LibraryType(row["library_type"]))  # type: ignore

                    sample_pooling_table["sample_name"].append(sample_name)
                    sample_pooling_table["library_name"].append(library_name)
                    sample_pooling_table["sample_pool"].append(sample_pool)

            library_table = pd.DataFrame(library_table_data)
            form.sample_pooling_table = pd.DataFrame(sample_pooling_table)
            form.sample_pooling_table["mux_type_id"] = form.mux_type.id if form.mux_type else None
            form.sample_pooling_table["mux_barcode"] = None

            form.workflow.tables["library_table"] = library_table
            form.workflow.tables["sample_pooling_table"] = form.sample_pooling_table
            return form.workflow.get_next_step(form).make_response()
        return route

