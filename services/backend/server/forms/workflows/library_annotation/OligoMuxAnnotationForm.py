import pandas as pd
from fastapi import Depends, Response

from opengsync_db import categories as C, models, SyncSession, queries as Q

from ....core import exceptions as exc, dependencies
from ....utils import parsing
from ....components import inputs
from ....components.tables import TextColumn, DuplicateCellValue, InvalidCellValue, CategoricalDropDown, DropdownColumn, MissingCellValue
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow
from .LibraryAnnotationWorkflowStep import LibraryAnnotationWorkflowStep

class OligoMuxAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-oligo_mux_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[  # type: ignore
        TextColumn("sample_name", "Sample Name", 170, required=True, read_only=True),
        TextColumn("sample_pool", "Multiplexing Pool", 170, required=True, read_only=True),
        CategoricalDropDown("kit", "Kit", 250, categories={}, required=False),
        TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length, clean_up_fnc=lambda x: parsing.make_alpha_numeric(x)),
        TextColumn("barcode", "Sequence", 200, max_length=models.Feature.sequence.type.length, clean_up_fnc=lambda x: parsing.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
        TextColumn("pattern", "Pattern", 180, max_length=models.Feature.pattern.type.length, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
        DropdownColumn("read", "Read", 80, choices=["R2", "R1"]),
    ])

    @classmethod
    def is_abc_hashed(cls, workflow: LibraryAnnotationWorkflow) -> bool:
        return C.MUXType.get(workflow.metadata.get("mux_type_id")) == C.MUXType.TENX_ABC_HASH

    @classmethod
    def is_applicable(cls, workflow: "LibraryAnnotationWorkflow") -> bool:
        return bool(workflow.tables["library_table"]["library_type_id"].isin([C.LibraryType.TENX_MUX_OLIGO.id]).any())
    
    @classmethod
    def get_mux_table(cls, sample_pooling_table: pd.DataFrame) -> pd.DataFrame:
        df = sample_pooling_table.copy()
        if "mux_read" not in df.columns:
            df["mux_read"] = None
        if "mux_pattern" not in df.columns:
            df["mux_pattern"] = None
        if "mux_barcode" not in df.columns:
            df["mux_barcode"] = None

        mux_data = {
            "sample_name": [],
            "sample_pool": [],
            "barcode": [],
            "pattern": [],
            "read": [],
        }
        for (sample_name, sample_pool, mux_barcode, mux_pattern, mux_read), _ in df.groupby(["sample_name", "sample_pool", "mux_barcode", "mux_pattern", "mux_read"], dropna=False, sort=False):
            mux_data["sample_name"].append(sample_name)
            mux_data["sample_pool"].append(sample_pool)
            mux_data["barcode"].append(mux_barcode)
            mux_data["pattern"].append(mux_pattern)
            mux_data["read"].append(mux_read)

        return pd.DataFrame(mux_data)

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: LibraryAnnotationWorkflow = Depends(LibraryAnnotationWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session)
        ) -> OligoMuxAnnotationForm:
            kits_mapping = {kit.identifier: f"[{kit.identifier}] {kit.name}" for kit in session.get_all(Q.feature_kit.select(type=C.FeatureType.CMO).order_by(models.FeatureKit.name.asc()), limit=None)}
            pooling_table = workflow.tables["sample_pooling_table"]
            pooling_table = pooling_table[pooling_table["mux_type_id"].isin([C.MUXType.TENX_OLIGO.id, C.MUXType.TENX_ABC_HASH.id])]
            mux_table = OligoMuxAnnotationForm.get_mux_table(pooling_table)
            form = cls(workflow=workflow)
            form.spreadsheet.set_data(mux_table)
            form.spreadsheet.columns["kit"].set_categories(kits_mapping)
            return form
        return dependency
    
    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: OligoMuxAnnotationForm = Depends(OligoMuxAnnotationForm.Init()),
        ) -> Response:
            df = form.workflow.tables["sample_pooling_table"]
            df = df.drop_duplicates(subset=["sample_name"]).rename(columns={"sample_name": "sample_name"})
            form.spreadsheet.set_data(df)
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: OligoMuxAnnotationForm = Depends(OligoMuxAnnotationForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session)
        ) -> Response:
            df = form.spreadsheet.data
            kit_feature = pd.notna(df["kit"]) & pd.notna(df["feature"])
            custom_feature = pd.notna(df["barcode"]) & pd.notna(df["pattern"]) & pd.notna(df["read"])
            invalid_feature = (pd.notna(df["kit"]) | pd.notna(df["feature"])) & (pd.notna(df["barcode"]) | pd.notna(df["pattern"]) | pd.notna(df["read"]))
            
            kit_identifiers = df["kit"].dropna().unique().tolist()
            kits: dict[str, tuple[models.FeatureKit, pd.DataFrame]] = dict()
            
            df["kit_id"] = None
            for identifier in kit_identifiers:
                kit = session.get_one(Q.feature_kit.select(identifier=identifier))
                kit_df = session.pd.get_feature_kit_features(kit.id)
                kits[identifier] = (kit, kit_df)
                df.loc[df["kit"] == identifier, "kit_id"] = kit.id

            duplicate_oligo = (
                (df.duplicated(subset=["sample_pool", "barcode", "pattern", "read"], keep=False) & custom_feature) |
                (df.duplicated(subset=["sample_pool", "kit", "feature"], keep=False) & kit_feature)
            )

            for identifier, (kit, kit_df) in kits.items():
                view = df[df["kit"] == identifier]
                kit_df["barcode"] = kit_df["sequence"]
                mask = kit_df["name"].isin(view["feature"])

                for _, kit_row in kit_df[mask].iterrows():
                    df.loc[
                        (df["kit"] == identifier) & (df["feature"] == kit_row["name"]),
                        ["barcode", "pattern", "read"]
                    ] = kit_row[["barcode", "pattern", "read"]].values
                    
            for idx, row in df.iterrows():
                # Not defined custom nor kit feature
                if kit_feature.at[idx]:
                    identifier = row["kit"]
                    kit, kit_df = kits[identifier]
                    if pd.notna(row["feature"]):
                        if row["feature"] not in kit_df["name"].values:
                            form.spreadsheet.add_error(idx, "feature", InvalidCellValue(f"Feature '{row['feature']}' not found in kit '{identifier}'"))
                            continue
                
                if (not custom_feature.at[idx] and not kit_feature.at[idx]):
                    form.spreadsheet.add_error(idx, "kit", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                    form.spreadsheet.add_error(idx, "feature", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                    form.spreadsheet.add_error(idx, "barcode", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                    form.spreadsheet.add_error(idx, "pattern", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                    form.spreadsheet.add_error(idx, "read", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))

                # Defined both custom and kit feature
                elif custom_feature.at[idx] and kit_feature.at[idx]:
                    form.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    form.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    form.spreadsheet.add_error(idx, "barcode", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    form.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    form.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))

                elif invalid_feature.at[idx]:
                    if pd.notna(row["kit"]):
                        form.spreadsheet.add_error(idx, "kit", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    if pd.notna(row["feature"]):
                        form.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    if pd.notna(row["barcode"]):
                        form.spreadsheet.add_error(idx, "barcode", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    if pd.notna(row["pattern"]):
                        form.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    if pd.notna(row["read"]):
                        form.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."))

                if duplicate_oligo.at[idx]:
                    form.spreadsheet.add_error(idx, "barcode", DuplicateCellValue("Definitions must be unique for each sample."))
                    form.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Definitions must be unique for each sample."))
                    form.spreadsheet.add_error(idx, "read", DuplicateCellValue("Definitions must be unique for each sample."))
                    form.spreadsheet.add_error(idx, "kit", DuplicateCellValue("Definitions must be unique for each sample."))
                    form.spreadsheet.add_error(idx, "feature", DuplicateCellValue("Definitions must be unique for each sample."))

            form.assert_valid()
            
            df["custom_feature"] = custom_feature
            df["kit_feature"] = kit_feature

            sample_pooling_table = workflow.tables["sample_pooling_table"]

            sample_pooling_table["mux_barcode"] = None
            sample_pooling_table["mux_pattern"] = None
            sample_pooling_table["mux_read"] = None
            sample_pooling_table["mux_kit"] = None
            sample_pooling_table["mux_feature"] = None

            for _, row in df.iterrows():
                sample_name = row["sample_name"]
                sample_pool = row["sample_pool"]
                sample_pooling_table.loc[(sample_pooling_table["sample_name"] == sample_name) & (sample_pooling_table["sample_pool"] == sample_pool), "mux_barcode"] = row["barcode"]
                sample_pooling_table.loc[(sample_pooling_table["sample_name"] == sample_name) & (sample_pooling_table["sample_pool"] == sample_pool), "mux_pattern"] = row["pattern"]
                sample_pooling_table.loc[(sample_pooling_table["sample_name"] == sample_name) & (sample_pooling_table["sample_pool"] == sample_pool), "mux_read"] = row["read"]
                sample_pooling_table.loc[(sample_pooling_table["sample_name"] == sample_name) & (sample_pooling_table["sample_pool"] == sample_pool), "mux_kit"] = row["kit"]
                sample_pooling_table.loc[(sample_pooling_table["sample_name"] == sample_name) & (sample_pooling_table["sample_pool"] == sample_pool), "mux_feature"] = row["feature"]

            if OligoMuxAnnotationForm.is_abc_hashed(form.workflow):
                sample_pooling_table["mux_type_id"] = C.MUXType.TENX_ABC_HASH.id
            else:
                sample_pooling_table["mux_type_id"] = C.MUXType.TENX_OLIGO.id

            library_table_data = {
                "library_name": [],
                "sample_name": [],
                "library_type": [],
                "library_type_id": [],
            }

            service_type_enum = C.ServiceType.get(form.workflow.metadata["service_type_id"])

            def add_library(sample_pool: str, library_type: C.LibraryType):
                library_table_data["library_name"].append(f"{sample_pool}_{library_type.identifier}")
                library_table_data["sample_name"].append(sample_pool)
                library_table_data["library_type"].append(library_type.name)
                library_table_data["library_type_id"].append(library_type.id)

            for (sample_pool,), _ in sample_pooling_table.groupby(["sample_pool"], sort=False):
                for library_type in service_type_enum.library_types:
                    add_library(sample_pool, library_type)  # type: ignore

                if form.workflow.metadata["antibody_capture"]:
                    if service_type_enum in C.ServiceType.get_flex_services():
                        add_library(sample_pool, C.LibraryType.TENX_SC_ABC_FLEX)  # type: ignore
                    else:
                        add_library(sample_pool, C.LibraryType.TENX_ANTIBODY_CAPTURE)  # type: ignore

                if form.workflow.metadata["vdj_b"]:
                    add_library(sample_pool, C.LibraryType.TENX_VDJ_B)  # type: ignore

                if form.workflow.metadata["vdj_t"]:
                    add_library(sample_pool, C.LibraryType.TENX_VDJ_T)  # type: ignore

                if form.workflow.metadata["vdj_t_gd"]:
                    add_library(sample_pool, C.LibraryType.TENX_VDJ_T_GD)  # type: ignore

                if form.workflow.metadata["crispr_screening"]:
                    add_library(sample_pool, C.LibraryType.TENX_CRISPR_SCREENING)  # type: ignore

            library_table = pd.DataFrame(library_table_data)
            library_table["seq_depth"] = None
                    
            kit_table = df[df["kit"].notna()][["kit"]].drop_duplicates().copy()
            kit_table["type_id"] = C.FeatureType.CMO.id
            kit_table["kit_id"] = None

            if kit_table.shape[0] > 0:
                if (existing_kit_table := form.workflow.tables.get("kit_table")) is None:  # type: ignore
                    form.workflow.tables["kit_table"] = kit_table
                else:
                    kit_table = pd.concat([kit_table[kit_table["type_id"] != C.FeatureType.CMO.id], existing_kit_table])
                    form.workflow.tables["kit_table"] = kit_table
            
            form.workflow.tables["sample_pooling_table"] = sample_pooling_table
            return form.workflow.get_next_step(form).make_response()
        return route

