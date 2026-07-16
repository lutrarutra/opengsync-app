import pandas as pd

from fastapi import Depends, Response, Query
from loguru import logger

from opengsync_db import categories as C, SyncSession, queries as Q, models

from ...core import dependencies, exceptions, responses
from ...components import inputs
from ...utils import parsing
from ...components.tables import IntegerColumn, TextColumn, DuplicateCellValue
from ..HTMXForm import RouteFunc, htmx_route, HTMXForm, FormFunc


class FlexMuxPrepAction(HTMXForm):
    template_path = "actions/flex-mux-prep.html"

    table = inputs.spreadsheet.SpreadsheetInputField(columns=[
        IntegerColumn("sample_id", "Sample ID", 100, required=True, read_only=True),
        IntegerColumn("library_id", "Library ID", 100, required=True, read_only=True),
        TextColumn("sample_pool", "Sample Pool", 300, required=True, read_only=True),
        TextColumn("sample_name", "Demultiplexed Name", 300, required=True, read_only=True),
        TextColumn("barcode_id", "Bardcode ID", 200, required=False, max_length=models.links.SampleLibraryLink.MAX_MUX_FIELD_LENGTH),
    ])

    def __init__(self, lab_prep: models.LabPrep, sample_table: pd.DataFrame, flex_table: pd.DataFrame):
        super().__init__()
        self.lab_prep = lab_prep
        self.sample_table = sample_table
        self.flex_table = flex_table
        self.post_url = responses.url_for("FlexMuxPrepAction.Submit").include_query_params(lab_prep_id=lab_prep.id)


    @classmethod
    def Init(cls) -> "FormFunc":
        def dependency(
            lab_prep_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            _ = Depends(dependencies.require_insider),
        ) -> "FlexMuxPrepAction":
            lab_prep = session.get_one(Q.lab_prep.select(id=lab_prep_id))
            sample_table = session.pd.get_lab_prep_pooling_table(lab_prep.id)
            sample_table = sample_table[sample_table["mux_type"].isin([C.MUXType.TENX_FLEX_PROBE])]
            flex_table = sample_table[
                (sample_table["mux_type"].isin([C.MUXType.TENX_FLEX_PROBE])) &
                (sample_table["library_type"].isin([C.LibraryType.TENX_SC_GEX_FLEX]))
            ].copy()

            flex_table["barcode_id"] = sample_table["mux"].apply(lambda x: x.get("barcode") if pd.notna(x) and isinstance(x, dict) else None)
            return cls(lab_prep=lab_prep, sample_table=sample_table, flex_table=flex_table)
        return dependency

    @htmx_route("GET")
    def Render(cls) -> RouteFunc:
        def route(
            form: "FlexMuxPrepAction" = Depends(FlexMuxPrepAction.Init()),
        ):
            return form.make_response()
        return route
    
    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "FlexMuxPrepAction" = Depends(FlexMuxPrepAction.Validate()),
        ) -> Response:
            df = form.table.data

            duplicate_barcode = df.duplicated(subset=["sample_pool", "barcode_id"], keep=False)
        
            for idx, row in df.iterrows():
                if pd.notna(row["barcode_id"]) and duplicate_barcode.at[idx]:
                    form.table.add_error(idx, "barcode_id", DuplicateCellValue("'Barcode ID' is duplicated in library."))

            if len(form.errors):
                raise exceptions.FormValidationException(form)
            
            form.flex_table["mux_barcode"] = parsing.map_columns(form.flex_table, df, ["sample_id", "library_id"], "barcode_id")
            if C.LibraryType.TENX_SC_ABC_FLEX in form.flex_table["library_type"].values:
                raise NotImplementedError("ABC Mux is not implemented")
            # if FlexABCForm.is_applicable(form):
            #     form = FlexABCForm(lab_prep=form.lab_prep, uuid=form.uuid)
            #     return form.make_response()

            # CommonFlexMuxForm.update_barcodes(form.flex_table)

            return responses.htmx_response(
                redirect=responses.url_for("lab_prep_page", lab_prep_id=form.lab_prep.id),
                flash=responses.flash("Changes saved!", "success"),
            )

        return route