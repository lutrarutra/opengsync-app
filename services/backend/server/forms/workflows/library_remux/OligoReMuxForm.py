from typing import Self

import pandas as pd
from fastapi import Depends, Response
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import orm

from opengsync_db import categories as C, models, SyncSession, queries as Q

from ....core import dependencies, exceptions as exc
from ....core.context import ctx
from ....utils import parsing
from ....components import inputs
from ....components.tables import (
    StaticSpreadsheet, TextColumn, DuplicateCellValue, InvalidCellValue,
    CategoricalDropDown, DropdownColumn, MissingCellValue,
)
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .LibraryRemuxWorkflow import LibraryRemuxWorkflow, LibraryRemuxWorkflowStep


class OligoLinkRow(BaseModel):
    sample_id: int
    mux_barcode: str | None = None
    mux_read: str | None = None
    mux_pattern: str | None = None


class OligoPoolApplyRow(BaseModel):
    sample_name: str
    mux_barcode: str | None = None
    mux_read: str | None = None
    mux_pattern: str | None = None


class PoolSampleRow(BaseModel):
    sample_id: int
    library_id: int


def _update_link_mux(
    session: SyncSession,
    sample_id: int,
    library_id: int,
    barcode: str | None,
    read: str | None,
    pattern: str | None,
) -> None:
    link = session.first(Q.links.get_sample_library_link(sample_id=sample_id, library_id=library_id))
    if link is None:
        logger.error(f"Could not find link for sample {sample_id} and library {library_id}")
        raise exc.NotFoundException("Sample-library link not found.")
    mux = dict(link.mux) if link.mux else {}
    mux["barcode"] = barcode
    mux["read"] = read
    mux["pattern"] = pattern
    link.mux = mux
    session.save(link)


class OligoReMuxForm(LibraryRemuxWorkflowStep):
    workflow: LibraryRemuxWorkflow
    template_path = "workflows/library_remux/oligo_annotation.html"
    apply_to_sample_pool = inputs.boolean.BooleanInputField(
        "Apply to all samples in pool",
        description="Will copy and apply the changes to all other sample-links in sample-pool. If you don't know what you are doing, leave it as is.",
        default=True,
    )
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

    def __init__(self, workflow: LibraryRemuxWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.pooling_table = pd.DataFrame()
        self.library_sample_pool_table = pd.DataFrame()

    @classmethod
    def build(cls, workflow: LibraryRemuxWorkflow, session: SyncSession) -> Self:
        library = session.get_one(
            Q.library.select(id=workflow.library_id),
            options=[orm.selectinload(models.Library.sample_links)],
        )
        kits_mapping = {
            kit.identifier: f"[{kit.identifier}] {kit.name}"
            for kit in session.get_all(
                Q.feature_kit.select(type=C.FeatureType.CMO).order_by(models.FeatureKit.name.asc()),
                limit=None,
            )
        }

        rows = [
            {
                "sample_id": link.sample_id,
                "sample_name": link.sample.name,
                "barcode": link.mux.get("barcode") if link.mux is not None else None,
                "pattern": link.mux.get("pattern") if link.mux is not None else None,
                "read": link.mux.get("read") if link.mux is not None else None,
                "library_id": library.id,
                "sample_pool": library.sample_name,
            }
            for link in library.sample_links
        ]
        pooling_table = pd.DataFrame(
            rows,
            columns=["sample_id", "sample_name", "barcode", "pattern", "read", "library_id", "sample_pool"],
        )
        mux_table = pooling_table[["sample_name", "sample_pool", "barcode", "pattern", "read"]].copy()

        pool_table = session.pd.get_library_sample_pool(library.id, expand_mux=True)
        if not pool_table.empty:
            pool_table = pool_table.sort_values(by=["sample_name", "library_name", "sample_pool"])
        for col in ("barcode", "pattern", "read"):
            if col not in pool_table.columns:
                pool_table[col] = None

        form = cls(workflow=workflow)
        form.pooling_table = pooling_table
        form.library_sample_pool_table = pool_table
        form._context["library"] = library
        form._context["library_sample_pool_table"] = StaticSpreadsheet(
            df=pool_table,
            columns=[
                TextColumn("sample_name", "Demultiplexed Name", 170),
                TextColumn("sample_pool", "Sample Pool Name", 170),
                TextColumn("library_name", "Library Name", 170),
                TextColumn("barcode", "Sequence", 150),
                TextColumn("pattern", "Pattern", 200),
                TextColumn("read", "Read", 100),
            ],
            id="example-spreadsheet-library-sample-pool-table",
        )
        form.spreadsheet.columns["kit"].set_categories(kits_mapping)
        form.spreadsheet.configure(
            csrf_token=form.csrf_token_value,
            post_url=form.post_url,
            df=mux_table,
        )
        if ctx.request.method == "GET" and not pool_table.empty:
            form.apply_to_sample_pool.data = bool(
                pool_table.duplicated(["sample_name", "barcode", "pattern", "read"], keep=False).all()
            )
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: LibraryRemuxWorkflow = Depends(LibraryRemuxWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> OligoReMuxForm:
            return cls.build(workflow, session)
        return dependency

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: OligoReMuxForm = Depends(OligoReMuxForm.Validate()),
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

            df["mux_read"] = df["read"]
            df["mux_barcode"] = df["barcode"]
            df["mux_pattern"] = df["pattern"]

            pooling_table = form.pooling_table.copy()
            pooling_table["mux_read"] = parsing.map_columns(pooling_table, df, ["sample_name", "sample_pool"], "mux_read")
            pooling_table["mux_barcode"] = parsing.map_columns(pooling_table, df, ["sample_name", "sample_pool"], "mux_barcode")
            pooling_table["mux_pattern"] = parsing.map_columns(pooling_table, df, ["sample_name", "sample_pool"], "mux_pattern")

            if not form.apply_to_sample_pool.data:
                for _, row in parsing.safe_iter(pooling_table, OligoLinkRow):
                    _update_link_mux(
                        session,
                        sample_id=row.sample_id,
                        library_id=form.workflow.library_id,
                        barcode=row.mux_barcode,
                        read=row.mux_read,
                        pattern=row.mux_pattern,
                    )
            else:
                for _, row in parsing.safe_iter(df, OligoPoolApplyRow):
                    matches = form.library_sample_pool_table[
                        form.library_sample_pool_table["sample_name"] == row.sample_name
                    ]
                    for _, pool_row in parsing.safe_iter(matches, PoolSampleRow):
                        _update_link_mux(
                            session,
                            sample_id=pool_row.sample_id,
                            library_id=pool_row.library_id,
                            barcode=row.mux_barcode,
                            read=row.mux_read,
                            pattern=row.mux_pattern,
                        )

            return form.workflow.complete_to_library(tab="library-multiplexing-tab")
        return route
