import pandas as pd
from pydantic import BaseModel
from fastapi import Depends
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ...core import dependencies, exceptions as exc, responses
from ...utils import parsing
from ...components import inputs
from ...components.tables.spreadsheet import (
    TextColumn, CategoricalDropDown, DropdownColumn,
    DuplicateCellValue, InvalidCellValue, MissingCellValue,
)
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class LibraryFeaturesAction(HTMXForm):
    template_path = "forms/library-features-table.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        CategoricalDropDown("kit", "Kit", 250, categories={}, required=False),
        TextColumn("identifier", "Identifier", 150, max_length=models.Feature.identifier.type.length, required=True),
        TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length),
        TextColumn("sequence", "Sequence", 150, max_length=models.Feature.sequence.type.length),
        TextColumn("pattern", "Pattern", 200, max_length=models.Feature.pattern.type.length),
        DropdownColumn("read", "Read", 100, choices=["R2", "R1"]),
    ])

    def __init__(self, library: models.Library) -> None:
        super().__init__()
        self.library = library
        self._context["library"] = library
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", library_id=library.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            library_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "LibraryFeaturesAction":
            library = session.get_one(
                Q.library.select(id=library_id),
                options=[orm.selectinload(models.Library.features)],
            )
            form = LibraryFeaturesAction(library=library)

            # Build kit dropdown
            kit_mapping = {
                kit.identifier: f"[{kit.identifier}] {kit.name}"
                for kit in session.get_all(
                    Q.feature_kit.select(type=C.FeatureType.ANTIBODY),
                    order_by=models.FeatureKit.name.desc(),
                    limit=None,
                )
            }
            form.spreadsheet.columns["kit"].set_categories(kit_mapping)

            # Pre-fill with existing features
            df = session.pd.get_library_features(library.id).rename(columns={
                "feature_name": "feature",
                "kit_identifier": "kit",
            })

            form.spreadsheet.configure(
                csrf_token=form.csrf_token_value,
                post_url=form.post_url,
                df=df,
            )
            return form
        return dependency

    @htmx_route("GET", "/{library_id}/edit-features")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "LibraryFeaturesAction" = Depends(LibraryFeaturesAction.Init()),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{library_id}/edit-features")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LibraryFeaturesAction" = Depends(LibraryFeaturesAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_insider),
        ) -> responses.Response:
            df = form.spreadsheet.data

            kit_feature = pd.notna(df["kit"])
            custom_feature = pd.notna(df["feature"]) & pd.notna(df["sequence"]) & pd.notna(df["pattern"]) & pd.notna(df["read"])
            duplicate_identifier = pd.notna(df["identifier"]) & df.duplicated(subset=["identifier"], keep=False)
            duplicate_name = pd.notna(df["feature"]) & df.duplicated(subset=["feature"], keep=False)
            duplicated = df.duplicated(keep=False)

            kit_identifiers = df["kit"].dropna().unique().tolist()
            kits: dict[str, tuple[models.FeatureKit, pd.DataFrame]] = {}

            df["kit_id"] = pd.Series([None] * len(df), dtype="Int64")
            df["feature_id"] = None

            for identifier in kit_identifiers:
                kit = session.get_one(Q.feature_kit.select(identifier=identifier))
                kit_df = session.pd.get_feature_kit_features(kit.id)
                kits[identifier] = (kit, kit_df)
                df.loc[df["kit"] == identifier, "kit_id"] = kit.id

            # Auto-fill sequence/pattern/read from kit features
            for identifier, (kit, kit_df) in kits.items():
                mask = kit_df["name"].isin(df[df["kit"] == identifier]["feature"])
                for _, kit_row in kit_df[mask].iterrows():
                    df.loc[
                        (df["kit"] == identifier) & (df["feature"] == kit_row["name"]),
                        ["sequence", "pattern", "read"]
                    ] = kit_row[["sequence", "pattern", "read"]].values
                    df.loc[
                        (df["kit"] == identifier) & (df["identifier"] == kit_row["identifier"]),
                        ["sequence", "pattern", "read"]
                    ] = kit_row[["sequence", "pattern", "read"]].values

            class RowSchema(BaseModel):
                feature_id: float | None
                identifier: str | None
                feature: str | None
                sequence: str | None
                pattern: str | None
                read: str | None
                kit: str | None

            for idx, row in parsing.safe_iter(df, RowSchema):
                if duplicate_identifier.at[idx]:
                    form.spreadsheet.add_error(idx, "identifier", DuplicateCellValue("duplicate feature definition"))
                if duplicate_name.at[idx]:
                    form.spreadsheet.add_error(idx, "feature", DuplicateCellValue("duplicate feature name"))
                if duplicated.at[idx]:
                    form.spreadsheet.add_error(idx, "kit", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "feature", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "read", DuplicateCellValue("duplicate feature definition"))

                if kit_feature.at[idx]:
                    assert row.kit is not None
                    kit, kit_df = kits[row.kit]
                    if row.identifier is not None:
                        if row.identifier not in kit_df["identifier"].values:
                            df.at[idx, "feature_id"] = kit_df.loc[kit_df["identifier"] == row.identifier, "feature_id"].values[0]
                            form.spreadsheet.add_error(idx, "identifier", InvalidCellValue(f"Identifier '{row.identifier}' not found in kit '{row.kit}'"))
                            continue
                    if row.feature is not None:
                        if row.feature not in kit_df["name"].values:
                            form.spreadsheet.add_error(idx, "feature", InvalidCellValue(f"Feature '{row.feature}' not found in kit '{row.kit}'"))
                            continue

                elif not custom_feature.at[idx] and not kit_feature.at[idx]:
                    for col in ["kit", "feature", "sequence", "pattern", "read"]:
                        form.spreadsheet.add_error(idx, col, MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))

                elif custom_feature.at[idx] and kit_feature.at[idx]:
                    for col in ["kit", "feature", "sequence", "pattern", "read"]:
                        form.spreadsheet.add_error(idx, col, InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))

                elif custom_feature.at[idx]:
                    idx_seq = (df["sequence"] == row.sequence) & (df["pattern"] == row.pattern) & (df["read"] == row.read)
                    if df[idx_seq].shape[0] > 1:
                        form.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination."))
                        form.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination."))
                        form.spreadsheet.add_error(idx, "read", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination."))

                elif kit_feature.at[idx]:
                    idx_kit_feature = True
                    if row.kit is not None:
                        idx_kit_feature = idx_kit_feature & (df["kit"] == row.kit)
                    if row.feature is not None:
                        idx_kit_feature = idx_kit_feature & (df["feature"] == row.feature)
                    if df[idx_kit_feature].shape[0] > 1:
                        form.spreadsheet.add_error(idx, "feature", DuplicateCellValue("Duplicate 'Kit' + 'Feature' specified."))

            form.assert_valid()

            # Save features
            form.library.features = []

            class FeatureRow(BaseModel):
                feature_id: float | None
                identifier: str | None
                feature: str
                sequence: str
                pattern: str
                read: str

            for _, row in parsing.safe_iter(df, FeatureRow):
                if row.feature_id is not None:
                    feature = session.get_one(Q.feature.select(id=int(row.feature_id)))
                    form.library.features.append(feature)
                else:
                    form.library.features.append(Q.feature.create(
                        identifier=row.identifier,
                        name=row.feature,
                        sequence=row.sequence,
                        pattern=row.pattern,
                        read=row.read,
                        type=C.FeatureType.ANTIBODY,
                    ))

            session.save(form.library)

            return responses.htmx_response(
                redirect=responses.url_for("library_page", library_id=form.library.id),
                flash=responses.flash("Changes Saved!", "success"),
            )
        return route