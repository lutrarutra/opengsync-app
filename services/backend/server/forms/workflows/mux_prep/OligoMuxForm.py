from typing import Self

import pandas as pd
from fastapi import Depends, Response
from loguru import logger
from pydantic import BaseModel

from opengsync_db import categories as C, models, SyncSession, queries as Q

from ....core import dependencies, exceptions as exc
from ....utils import parsing
from ....components import inputs
from ....components.tables import (
    TextColumn, DuplicateCellValue, InvalidCellValue, CategoricalDropDown,
    DropdownColumn, MissingCellValue,
)
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .MuxPrepWorkflow import MuxPrepWorkflow, MuxPrepWorkflowStep


class MuxGroupSchema(BaseModel):
    sample_name: str
    sample_pool: str
    mux_barcode: str | None = None
    mux_pattern: str | None = None
    mux_read: str | None = None


class OligoMuxForm(MuxPrepWorkflowStep):
    workflow: MuxPrepWorkflow
    template_path = "workflows/mux_prep/mux_prep-oligo_mux_annotation.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(
        columns=[
            TextColumn("sample_name", "Sample Name", 170, required=True, read_only=True),
            TextColumn("sample_pool", "Multiplexing Pool", 170, required=True, read_only=True),
            CategoricalDropDown("kit", "Kit", 250, categories={}, required=False),
            TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length, clean_up_fnc=lambda x: parsing.make_alpha_numeric(x)),
            TextColumn("barcode", "Sequence", 200, max_length=models.Feature.sequence.type.length, clean_up_fnc=lambda x: parsing.make_alpha_numeric(x, keep=[], replace_white_spaces_with="")),
            TextColumn("pattern", "Pattern", 180, max_length=models.Feature.pattern.type.length, clean_up_fnc=lambda x: x.strip() if pd.notna(x) else None),
            DropdownColumn("read", "Read", 80, choices=["R2", "R1"]),
        ],
        allow_new_rows=False,
    )

    @staticmethod
    def get_mux_table(sample_pooling_table: pd.DataFrame) -> pd.DataFrame:
        df = sample_pooling_table.copy()
        if "mux_read" not in df.columns:
            df["mux_read"] = None
        if "mux_pattern" not in df.columns:
            df["mux_pattern"] = None
        if "mux_barcode" not in df.columns:
            df["mux_barcode"] = None

        mux_data: dict[str, list] = {
            "sample_name": [],
            "sample_pool": [],
            "barcode": [],
            "pattern": [],
            "read": [],
        }
        for key, _ in parsing.safe_groupby(
            df,
            ["sample_name", "sample_pool", "mux_barcode", "mux_pattern", "mux_read"],
            MuxGroupSchema,
            sort=False,
            dropna=False,
        ):
            mux_data["sample_name"].append(key.sample_name)
            mux_data["sample_pool"].append(key.sample_pool)
            mux_data["barcode"].append(key.mux_barcode)
            mux_data["pattern"].append(key.mux_pattern)
            mux_data["read"].append(key.mux_read)

        return pd.DataFrame(mux_data)

    @classmethod
    def build(cls, workflow: MuxPrepWorkflow, session: SyncSession) -> Self:
        kits_mapping = {
            kit.identifier: f"[{kit.identifier}] {kit.name}"
            for kit in session.get_all(
                Q.feature_kit.select(type=C.FeatureType.CMO).order_by(models.FeatureKit.name.asc()),
                limit=None,
            )
        }
        pooling_table = session.pd.get_lab_prep_pooling_table(workflow.lab_prep_id, expand_mux=True)
        pooling_table = pooling_table[pooling_table["mux_type_id"].isin([C.MUXType.TENX_OLIGO.id, C.MUXType.TENX_ABC_HASH.id])]
        mux_table = cls.get_mux_table(pooling_table)

        form = cls(workflow=workflow)
        form.spreadsheet.columns["kit"].set_categories(kits_mapping)
        form.spreadsheet.configure(
            csrf_token=form.csrf_token_value,
            post_url=form.post_url,
            df=mux_table,
        )
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: MuxPrepWorkflow = Depends(MuxPrepWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> OligoMuxForm:
            return cls.build(workflow, session)
        return dependency

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: OligoMuxForm = Depends(OligoMuxForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: OligoMuxForm = Depends(OligoMuxForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            df = form.spreadsheet.data
            kit_feature = pd.notna(df["kit"]) & pd.notna(df["feature"])
            custom_feature = pd.notna(df["barcode"]) & pd.notna(df["pattern"]) & pd.notna(df["read"])
            invalid_feature = (
                (pd.notna(df["kit"]) | pd.notna(df["feature"]))
                & (pd.notna(df["barcode"]) | pd.notna(df["pattern"]) | pd.notna(df["read"]))
            )

            kit_identifiers = df["kit"].dropna().unique().tolist()
            kits: dict[str, tuple[models.FeatureKit, pd.DataFrame]] = {}

            df["kit_id"] = None
            for identifier in kit_identifiers:
                kit = session.get_one(Q.feature_kit.select(identifier=identifier))
                kit_df = session.pd.get_feature_kit_features(kit.id)
                kits[identifier] = (kit, kit_df)
                df.loc[df["kit"] == identifier, "kit_id"] = kit.id

            duplicate_oligo = (
                (df.duplicated(subset=["sample_pool", "barcode", "pattern", "read"], keep=False) & custom_feature)
                | (df.duplicated(subset=["sample_pool", "kit", "feature"], keep=False) & kit_feature)
            )

            for identifier, (kit, kit_df) in kits.items():
                view = df[df["kit"] == identifier]
                kit_df["barcode"] = kit_df["sequence"]
                mask = kit_df["name"].isin(view["feature"])

                for _, kit_row in kit_df[mask].iterrows():
                    df.loc[
                        (df["kit"] == identifier) & (df["feature"] == kit_row["name"]),
                        ["barcode", "pattern", "read"],
                    ] = kit_row[["barcode", "pattern", "read"]].values

            xor_message = "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."
            both_message = "must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified, not both."

            for idx, row in df.iterrows():
                if kit_feature.at[idx]:
                    identifier = row["kit"]
                    kit, kit_df = kits[identifier]
                    if pd.notna(row["feature"]) and row["feature"] not in kit_df["name"].values:
                        form.spreadsheet.add_error(
                            idx, "feature",
                            InvalidCellValue(f"Feature '{row['feature']}' not found in kit '{identifier}'"),
                        )
                        continue

                if not custom_feature.at[idx] and not kit_feature.at[idx]:
                    for col in ("kit", "feature", "barcode", "pattern", "read"):
                        form.spreadsheet.add_error(idx, col, MissingCellValue(xor_message))
                elif custom_feature.at[idx] and kit_feature.at[idx]:
                    for col in ("kit", "feature", "barcode", "pattern", "read"):
                        form.spreadsheet.add_error(idx, col, InvalidCellValue(both_message))
                elif invalid_feature.at[idx]:
                    if pd.notna(row["kit"]):
                        form.spreadsheet.add_error(idx, "kit", InvalidCellValue(both_message))
                    if pd.notna(row["feature"]):
                        form.spreadsheet.add_error(idx, "feature", InvalidCellValue(both_message))
                    if pd.notna(row["barcode"]):
                        form.spreadsheet.add_error(idx, "barcode", InvalidCellValue(both_message))
                    if pd.notna(row["pattern"]):
                        form.spreadsheet.add_error(idx, "pattern", InvalidCellValue(both_message))
                    if pd.notna(row["read"]):
                        form.spreadsheet.add_error(idx, "read", InvalidCellValue(both_message))

                if duplicate_oligo.at[idx]:
                    for col in ("barcode", "pattern", "read", "kit", "feature"):
                        form.spreadsheet.add_error(idx, col, DuplicateCellValue("Definitions must be unique for each sample."))

            form.assert_valid()

            pooling_table = session.pd.get_lab_prep_pooling_table(form.workflow.lab_prep_id, expand_mux=True)
            pooling_table = pooling_table[
                pooling_table["mux_type_id"].isin([C.MUXType.TENX_OLIGO.id, C.MUXType.TENX_ABC_HASH.id])
            ]
            pooling_table["mux_read"] = parsing.map_columns(pooling_table, df, ["sample_name", "sample_pool"], "read")
            pooling_table["mux_barcode"] = parsing.map_columns(pooling_table, df, ["sample_name", "sample_pool"], "barcode")
            pooling_table["mux_pattern"] = parsing.map_columns(pooling_table, df, ["sample_name", "sample_pool"], "pattern")

            for _, row in pooling_table.iterrows():
                sample_id = int(row["sample_id"])
                library_id = int(row["library_id"])
                link = session.first(Q.links.get_sample_library_link(sample_id=sample_id, library_id=library_id))
                if link is None:
                    logger.error(f"Could not find link for sample {sample_id} and library {library_id}")
                    raise exc.ItemNotFoundException("Sample-library link not found.")

                mux = dict(link.mux) if link.mux else {}
                mux["barcode"] = row["mux_barcode"] if pd.notna(row["mux_barcode"]) else None
                mux["read"] = row["mux_read"] if pd.notna(row["mux_read"]) else None
                mux["pattern"] = row["mux_pattern"] if pd.notna(row["mux_pattern"]) else None
                link.mux = mux
                session.save(link)

            return form.workflow.complete_to_lab_prep()
        return route
