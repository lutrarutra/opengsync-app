from typing import cast

import pandas as pd
from fastapi import Depends, Response

from opengsync_db import models, categories as C, SyncSession, queries as Q

from ....core import dependencies, exceptions as exc
from .... import utils
from ....components import inputs
from ....components.tables import TextColumn, DropdownColumn, DBObjectColumn, DuplicateCellValue, InvalidCellValue, MissingCellValue
from ...HTMXForm import RouteFunc, htmx_route
from ...common import kit_columns
from .LibraryAnnotationWorkflow import LibraryAnnotationWorkflow, LibraryAnnotationWorkflowStep

SAMPLE_COLUMN = "Sample"


class FeatureAnnotationForm(LibraryAnnotationWorkflowStep):
    workflow: LibraryAnnotationWorkflow
    template_path = "workflows/library_annotation/sas-feature_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        # Samples (or pools) of the antibody capture libraries, existing samples by "name [id]", others by "name [new]"
        DBObjectColumn(("sample_id", "sample_name"), SAMPLE_COLUMN, 170, categories={}, required=False),
        kit_columns.feature_kit_column("kit_id", "Kit", 250, types=[C.FeatureType.ANTIBODY]),
        TextColumn("identifier", "Identifier", 150, max_length=models.Feature.identifier.type.length, required=False, clean_up_fnc=utils.parsing.normalize_to_ascii, validation_fnc=utils.parsing.check_string),
        TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length),
        TextColumn("sequence", "Sequence", 150, max_length=models.Feature.sequence.type.length, clean_up_fnc=utils.barcodes.clean_sequence, validation_fnc=utils.barcodes.check_sequence),
        TextColumn("pattern", "Pattern", 200, max_length=models.Feature.pattern.type.length),
        DropdownColumn("read", "Read", 100, choices=["R2", "R1"]),
    ])

    @classmethod
    def is_applicable(cls, workflow: LibraryAnnotationWorkflow) -> bool:
        return bool(workflow.tables["library_table"]["library_type_id"].isin(
            [C.LibraryType.TENX_ANTIBODY_CAPTURE.id, C.LibraryType.TENX_SC_ABC_FLEX.id]
        ).any())

    def __init__(self, workflow: LibraryAnnotationWorkflow) -> None:
        super().__init__(workflow)
        self.spreadsheet.configure(csrf_token=self.csrf_token_value, post_url=self.post_url)
        self.library_table = self.workflow.tables["library_table"]
        self.abc_libraries = self.library_table[
            self.library_table["library_type_id"].isin(
                [C.LibraryType.TENX_ANTIBODY_CAPTURE.id, C.LibraryType.TENX_SC_ABC_FLEX.id]
            )
        ]
        self.abc_samples = self.abc_libraries["sample_name"].unique().tolist()
        # Library sample names are samples, or pools of multiplexed samples (which are never existing samples)
        self.sample_ids = self.set_sample_options(cast(DBObjectColumn, self.spreadsheet.columns[SAMPLE_COLUMN]), self.abc_samples)

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: FeatureAnnotationForm = Depends(FeatureAnnotationForm.Init()),
        ) -> Response:
            feature_table = form.workflow.tables["feature_table"].copy()
            # feature_table is keyed by library; the spreadsheet by the library's sample (pool) name
            # One row per sample for multiplexed pools: the pool's library name repeats
            library_sample_map = form.abc_libraries.drop_duplicates("library_name").set_index("library_name")["sample_name"]
            feature_table["sample_name"] = feature_table["library_name"].map(library_sample_map)
            feature_table["sample_id"] = feature_table["sample_name"].map(form.sample_ids)
            form.spreadsheet.set_data(feature_table)
            return form.make_response()
        return route
        
    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: FeatureAnnotationForm = Depends(FeatureAnnotationForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> Response:
            df = form.spreadsheet.data
            mentioned_abc_libraries = form.abc_libraries["sample_name"].isin(df["sample_name"])
            if pd.notna(df["sample_name"]).any() and not mentioned_abc_libraries.all():
                unmentioned = form.abc_libraries[~mentioned_abc_libraries]["sample_name"].values.tolist()
                form.spreadsheet.add_general_error(f"No features assigned to samples: {unmentioned}")
                raise exc.FormValidationException(form)
            
            kit_feature = pd.notna(df["kit_id"])
            custom_feature = pd.notna(df["feature"]) & pd.notna(df["sequence"]) & pd.notna(df["pattern"]) & pd.notna(df["read"])
            duplicate_identifier = pd.notna(df["identifier"]) & df.duplicated(subset=["identifier", "sample_name"], keep=False)
            duplicate_name = pd.notna(df["feature"]) & df.duplicated(subset=["feature", "sample_name"], keep=False)
            duplicated = df.duplicated(keep=False)

            kits: dict[int, tuple[models.FeatureKit, pd.DataFrame]] = dict()
            for kit_id in df["kit_id"].dropna().unique().tolist():
                kit = session.get_one(Q.feature_kit.select(id=int(kit_id)))
                kit_df = session.get_pandas(
                    Q.pd.feature_kit_features(kit.id),
                    limit=None,
                )
                kits[kit.id] = (kit, kit_df)
            df["kit"] = df["kit_id"].map(lambda kit_id: kits[int(kit_id)][0].identifier if pd.notna(kit_id) else None)

            for kit_id, (kit, kit_df) in kits.items():
                view = df[df["kit_id"].eq(kit_id).fillna(False)]
                mask = kit_df["name"].isin(view["feature"])

                for _, kit_row in kit_df[mask].iterrows():
                    df.loc[
                        df["kit_id"].eq(kit_id).fillna(False) & df["feature"].eq(kit_row["name"]).fillna(False),
                        ["sequence", "pattern", "read"]
                    ] = kit_row[["sequence", "pattern", "read"]].values

                    df.loc[
                        df["kit_id"].eq(kit_id).fillna(False) & df["identifier"].eq(kit_row["identifier"]).fillna(False),
                        ["sequence", "pattern", "read"]
                    ] = kit_row[["sequence", "pattern", "read"]].values

            for idx, row in df.iterrows():
                if duplicate_identifier.at[idx]:
                    form.spreadsheet.add_error(idx, "identifier", DuplicateCellValue("duplicate feature definition"))

                if duplicate_name.at[idx]:
                    form.spreadsheet.add_error(idx, "feature", DuplicateCellValue("duplicate feature name"))

                if duplicated.at[idx]:
                    form.spreadsheet.add_error(idx, SAMPLE_COLUMN, DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "kit_id", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "feature", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "read", DuplicateCellValue("duplicate feature definition"))

                if kit_feature.at[idx]:
                    identifier = row["kit"]
                    kit, kit_df = kits[int(row["kit_id"])]
                    if pd.notna(row["identifier"]):
                        if row["identifier"] not in kit_df["identifier"].values:
                            form.spreadsheet.add_error(idx, "identifier", InvalidCellValue(f"Identifier '{row['identifier']}' not found in kit '{identifier}'"))
                            continue
                    if pd.notna(row["feature"]):
                        if row["feature"] not in kit_df["name"].values:
                            form.spreadsheet.add_error(idx, "feature", InvalidCellValue(f"Feature '{row['feature']}' not found in kit '{identifier}'"))
                            continue

                # Not defined custom nor kit feature
                elif (not custom_feature.at[idx] and not kit_feature.at[idx]):
                    form.spreadsheet.add_error(idx, "kit_id", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                    form.spreadsheet.add_error(idx, "feature", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                    form.spreadsheet.add_error(idx, "sequence", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                    form.spreadsheet.add_error(idx, "pattern", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))
                    form.spreadsheet.add_error(idx, "read", MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))

                # Defined both custom and kit feature
                elif custom_feature.at[idx] and kit_feature.at[idx]:
                    form.spreadsheet.add_error(idx, "kit_id", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    form.spreadsheet.add_error(idx, "feature", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    form.spreadsheet.add_error(idx, "sequence", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    form.spreadsheet.add_error(idx, "pattern", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))
                    form.spreadsheet.add_error(idx, "read", InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))

                elif custom_feature.at[idx]:
                    idx_sample_name = df["sample_name"] == row["sample_name"]
                    idx_sequence = df["sequence"] == row["sequence"]
                    idx_pattern = df["pattern"] == row["pattern"]
                    idx_read = df["read"] == row["read"]

                    _idx = idx_sequence & idx_pattern & idx_read
                    if pd.notna(row["sample_name"]):
                        _idx = _idx & idx_sample_name

                    if df[_idx].shape[0] > 1:
                        form.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination in same library."))
                        form.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination in same library."))
                        form.spreadsheet.add_error(idx, "read", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination in same library."))

                elif kit_feature.at[idx]:
                    idx_sample_name = df["sample_name"] == row["sample_name"]
                    idx_kit = df["kit_id"].eq(row["kit_id"]).fillna(False)
                    idx_feature = df["feature"] == row["feature"]
                    idx = True
                    if pd.notna(row["sample_name"]):
                        idx = idx & idx_sample_name
                    if pd.notna(row["kit_id"]):
                        idx = idx & idx_kit
                    if pd.notna(row["feature"]):
                        idx = idx & idx_feature
                    
                    if df[idx].shape[0] > 1:
                        form.spreadsheet.add_error(idx, "feature", DuplicateCellValue("Duplicate 'Kit' + 'Feature' specified for same library."))

            form.assert_valid()
            
            library_sample_map = form.abc_libraries.set_index("sample_name").to_dict()["library_name"]
            df["library_name"] = df["sample_name"].map(library_sample_map)
            feature_table = form.get_feature_table(df, kits)
        
            if (kit_table := form.workflow.tables.get("kit_table")) is None:  # type: ignore
                kit_table = feature_table.loc[feature_table["kit"].notna(), ["kit", "kit_id"]].drop_duplicates().copy().rename(columns={"kit": "name"})
                kit_table["type_id"] = C.FeatureType.ANTIBODY.id
                form.workflow.tables["kit_table"] = kit_table
            else:
                _kit_table = feature_table.loc[feature_table["kit"].notna(), ["kit", "kit_id"]].drop_duplicates().copy().rename(columns={"kit": "name"})
                _kit_table["type_id"] = C.FeatureType.ANTIBODY.id
                kit_table = pd.concat([kit_table[kit_table["type_id"] != C.FeatureType.ANTIBODY.id], _kit_table])
                form.workflow.tables["kit_table"] = kit_table

            form.workflow.tables["feature_table"] = feature_table
            return form.workflow.get_next_step(form).make_response()
        return route
    

    def get_feature_table(self, df: pd.DataFrame, kits: dict[int, tuple[models.FeatureKit, pd.DataFrame]]) -> pd.DataFrame:
        feature_data = {
            "library_name": [],
            "kit": [],
            "identifier": [],
            "feature": [],
            "sequence": [],
            "pattern": [],
            "read": [],
            "kit_id": [],
            "feature_id": [],
        }

        def add_feature(
            library_name: str | None, feature_name: str,
            sequence: str, pattern: str, read: str,
            identifier: str | None,
            kit_name: str | None = None,
            kit_id: int | None = None,
            feature_id: int | None = None
        ):
            feature_data["library_name"].append(library_name)
            feature_data["kit_id"].append(kit_id)
            feature_data["feature_id"].append(feature_id)
            feature_data["identifier"].append(identifier)
            feature_data["kit"].append(kit_name)
            feature_data["feature"].append(feature_name)
            feature_data["sequence"].append(sequence)
            feature_data["pattern"].append(pattern)
            feature_data["read"].append(read)

        for _, row in df.iterrows():
            if pd.isna(row["kit_id"]):
                add_feature(
                    library_name=row["library_name"],
                    feature_name=row["feature"],
                    identifier=row["identifier"],
                    sequence=row["sequence"],
                    pattern=row["pattern"],
                    read=row["read"],
                )
                continue

            kit, kit_df = kits[int(row["kit_id"])]

            if pd.isna(row["identifier"]) and pd.isna(row["feature"]):
                for _, kit_row in kit_df.iterrows():
                    add_feature(
                        library_name=row["library_name"],
                        kit_id=kit.id,
                        kit_name=row["kit"],
                        identifier=kit_row["identifier"],
                        feature_id=kit_row["feature_id"],
                        feature_name=kit_row["name"],
                        sequence=kit_row["sequence"],
                        pattern=kit_row["pattern"],
                        read=kit_row["read"]
                    )
            elif pd.notna(row["identifier"]):
                for _, kit_row in kit_df[kit_df["identifier"] == row["identifier"]].iterrows():
                    add_feature(
                        library_name=row["library_name"],
                        kit_id=kit.id,
                        kit_name=row["kit"],
                        identifier=kit_row["identifier"],
                        feature_id=kit_row["feature_id"],
                        feature_name=kit_row["name"],
                        sequence=kit_row["sequence"],
                        pattern=kit_row["pattern"],
                        read=kit_row["read"]
                    )
            elif pd.notna(row["feature"]):
                for _, kit_row in kit_df[kit_df["name"] == row["feature"]].iterrows():
                    add_feature(
                        library_name=row["library_name"],
                        kit_id=kit.id,
                        kit_name=row["kit"],
                        identifier=kit_row["identifier"],
                        feature_id=kit_row["feature_id"],
                        feature_name=kit_row["name"],
                        sequence=kit_row["sequence"],
                        pattern=kit_row["pattern"],
                        read=kit_row["read"]
                    )

        return pd.DataFrame(feature_data)