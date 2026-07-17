import pandas as pd
from fastapi import Depends, Response

from opengsync_db import categories as C

from ....core import responses, exceptions as exc
from ....components import inputs
from ....components.tables import TextColumn, DropdownColumn, DuplicateCellValue
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep


class OpenSTAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-openst_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        DropdownColumn("sample_name", "Sample Name", 250, choices=[], required=True),
        TextColumn("image", "Image", 170, max_length=512, required=True),
    ])
    instructions = inputs.string.TextAreaInputField(
        "Instructions where to download images?",
        max_length=4096,
        description="Please provide instructions on where to download the images for the Visium libraries. Including link and password if required.",
    )

    @classmethod
    def is_applicable(cls, workflow: "LibraryAnnotationWorkflow") -> bool:
        return bool(workflow.tables["library_table"]["library_type_id"].isin([C.LibraryType.OPENST.id]).any())
    
    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.library_table = workflow.tables["library_table"]
        self.openst_libraries = self.library_table[self.library_table["library_type_id"].isin([C.LibraryType.OPENST.id])]
        self.openst_samples = self.openst_libraries["sample_name"].unique().tolist()

        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        def get_template() -> pd.DataFrame:
            data = {
                "sample_name": [],
                "image": [],
            }

            for _, row in self.openst_libraries.iterrows():
                data["sample_name"].append(row["sample_name"])
                data["image"].append(None)

            return pd.DataFrame(data)
        self.spreadsheet.set_data(get_template())
        self.spreadsheet.columns["sample_name"].set_choices(self.openst_samples)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: OpenSTAnnotationForm = Depends(OpenSTAnnotationForm.Init()),
        ) -> Response:
            library_properties_table = form.workflow.tables["library_properties_table"]
            form.spreadsheet.set_data(library_properties_table)
            form.instructions.data = form.workflow.metadata["visium_annotation_instructions"]
            return form.make_response()
        return route
    
    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: OpenSTAnnotationForm = Depends(OpenSTAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data
            for idx, row in df.iterrows():
                # TODO: check if using 'unique=True' in the spreadsheet input field would be better than this validation
                if (df["sample_name"] == row["sample_name"]).sum() > 1:
                    form.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue("'Sample Name' is a duplicate."))
                
            form.assert_valid()
            
            library_sample_map = form.openst_libraries.set_index("sample_name").to_dict()["library_name"]
            df["library_name"] = df["sample_name"].map(library_sample_map)

            form.workflow.add_comment(context="open_st_annotation", text=f"Images: {form.instructions.data}")
            form.workflow.metadata["visium_annotation_instructions"] = form.instructions.data

            if (library_properties_table := form.workflow.tables.get("library_properties_table")) is None:
                library_properties_table = df[["library_name", "sample_name"]].copy()

            library_properties_table["image"] = None

            for _, row in df.iterrows():
                library_properties_table.loc[library_properties_table["library_name"] == row["library_name"], "image"] = row["image"]
        
            form.workflow.tables["library_properties_table"] = library_properties_table
            form.workflow.metadata["visium_annotation_instructions"] = form.instructions.data
            return form.workflow.get_next_step(form).make_response()
        return route


