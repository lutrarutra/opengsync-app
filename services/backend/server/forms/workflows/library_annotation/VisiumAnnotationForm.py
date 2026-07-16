import pandas as pd
from fastapi import Depends, Response

from opengsync_db import categories as C

from ....core import responses, exceptions as exc
from ....components import inputs
from ....components.tables import TextColumn, DropdownColumn, DuplicateCellValue
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep


class VisiumAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-visium_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        DropdownColumn("sample_name", "Sample Name", 250, choices=[], required=True),
        TextColumn("image", "Image", 170, max_length=512, required=True),
        TextColumn("slide", "Slide", 170, max_length=32, required=True),
        TextColumn("area", "Area", 170, max_length=32, required=True),
        TextColumn("he_image", "H&E Image", 170, max_length=512, required=False),
    ])
    instructions = inputs.string.TextAreaInputField(
        "Instructions where to download images?",
        max_length=4096,
        description="Please provide instructions on where to download the images for the Visium libraries. Including link and password if required.",
    )

    @classmethod
    def is_applicable(cls, workflow: "LibraryAnnotationWorkflow") -> bool:
        return bool(workflow.tables["library_table"]["library_type_id"].isin([t.id for t in C.LibraryType.get_visium_library_types()]).any())
    
    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.library_table = workflow.tables["library_table"]
        self.visium_libraries = self.library_table[self.library_table["library_type_id"].isin([t.id for t in C.LibraryType.get_visium_library_types()])]
        self.visium_samples = self.visium_libraries["sample_name"].unique().tolist()

        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        def get_template() -> pd.DataFrame:
            data = {
                "sample_name": [],
                "image": [],
                "slide": [],
                "area": [],
                "he_image": [],
            }

            for _, row in self.visium_libraries.iterrows():
                data["sample_name"].append(row["sample_name"])
                data["image"].append(None)
                data["slide"].append(None)
                data["area"].append(None)
                data["he_image"].append(None)

            return pd.DataFrame(data)
        self.spreadsheet.set_data(get_template())
        self.spreadsheet.columns["sample_name"].set_choices(self.visium_samples)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: VisiumAnnotationForm = Depends(VisiumAnnotationForm.Init()),
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
        ) -> Response:
            library_properties_table = workflow.tables["library_properties_table"]
            form.spreadsheet.set_data(library_properties_table)
            form.instructions.data = workflow.metadata["visium_annotation_instructions"]
            return form.make_response()
        return route
    
    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
            form: VisiumAnnotationForm = Depends(VisiumAnnotationForm.Validate()),
        ) -> Response:
            df = form.spreadsheet.data

            for i, (idx, row) in enumerate(df.iterrows()):
                if (df["sample_name"] == row["sample_name"]).sum() > 1:
                    form.spreadsheet.add_error(idx, "sample_name", DuplicateCellValue("'Sample Name' is a duplicate."))
                
            form.assert_valid()
            
            library_sample_map = form.visium_libraries.set_index("sample_name").to_dict()["library_name"]
            df["library_name"] = df["sample_name"].map(library_sample_map)
            workflow.add_comment(context="visium_annotation", text=f"Images: {form.instructions.data}")
            workflow.metadata["visium_annotation_instructions"] = form.instructions.data

            if (library_properties_table := workflow.tables.get("library_properties_table")) is None:
                library_properties_table = df[["library_name", "sample_name"]].copy()

            library_properties_table["image"] = None
            library_properties_table["slide"] = None
            library_properties_table["area"] = None
            library_properties_table["he_image"] = None

            for _, row in df.iterrows():
                library_properties_table.loc[library_properties_table["library_name"] == row["library_name"], "image"] = row["image"]
                library_properties_table.loc[library_properties_table["library_name"] == row["library_name"], "slide"] = row["slide"]
                library_properties_table.loc[library_properties_table["library_name"] == row["library_name"], "area"] = row["area"]
                library_properties_table.loc[library_properties_table["library_name"] == row["library_name"], "he_image"] = row["he_image"]
            
            workflow.tables["library_properties_table"] = library_properties_table
            return workflow.get_next_step(form).make_response()
        return route


