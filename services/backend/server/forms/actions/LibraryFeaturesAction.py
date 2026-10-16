import pandas as pd
from pydantic import BaseModel
from fastapi import Depends
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from opengsync_db.core.blueprints import pd_transforms as T

from ...core import dependencies, exceptions as exc, responses
from ...utils import parsing
from ...components import inputs
from ...components.tables.spreadsheet import (
    TextColumn, DropdownColumn,
    DuplicateCellValue, InvalidCellValue, MissingCellValue,
)
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ..common import kit_columns


class LibraryFeaturesAction(HTMXForm):
    template_path = "forms/library-features-table.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        kit_columns.feature_kit_column("kit_id", "Kit", 250, types=[C.FeatureType.ANTIBODY]),
        TextColumn(
            "identifier", "Identifier", 150, max_length=models.Feature.identifier.type.length, required=True,
            clean_up_fnc=parsing.normalize_to_ascii, validation_fnc=parsing.check_string,
        ),
        TextColumn("feature", "Feature", 150, max_length=models.Feature.name.type.length),
        TextColumn(
            "sequence", "Sequence", 150, max_length=models.Feature.sequence.type.length,
            clean_up_fnc=lambda x: parsing.make_alpha_numeric(x, keep=[], replace_white_spaces_with=""),
        ),
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
            _=Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "LibraryFeaturesAction":
            library = session.get_one(
                Q.library.select(id=library_id),
                options=[orm.selectinload(models.Library.features)],
            )
            if library.type not in (C.LibraryType.TENX_ANTIBODY_CAPTURE, C.LibraryType.TENX_SC_ABC_FLEX):
                raise exc.BadRequestException("Only 10x Antibody Capture and 10x SC ABC Flex libraries have features that can be edited.")
            form = LibraryFeaturesAction(library=library)

            # Pre-fill with existing features
            df = T.library_features(
                session.get_pandas(Q.pd.library_features(library.id), limit=None)
            ).rename(columns={
                "feature_name": "feature",
                "kit_identifier": "kit",
            })
            df["kit_id"] = kit_columns.ids_column(df, "kit")

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
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{library_id}/edit-features")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "LibraryFeaturesAction" = Depends(LibraryFeaturesAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> responses.Response:
            df = form.spreadsheet.data
            # Kits are selected by id, identified by their identifier below
            df["kit"] = kit_columns.identifiers_column(df, "kit_id")

            kit_feature = pd.notna(df["kit"])
            custom_feature = pd.notna(df["feature"]) & pd.notna(df["sequence"]) & pd.notna(df["pattern"]) & pd.notna(df["read"])
            duplicate_identifier = pd.notna(df["identifier"]) & df.duplicated(subset=["identifier"], keep=False)
            duplicate_name = pd.notna(df["feature"]) & df.duplicated(subset=["feature"], keep=False)
            duplicated = df.duplicated(keep=False)

            kit_identifiers = df["kit"].dropna().unique().tolist()
            kits: dict[str, tuple[models.FeatureKit, pd.DataFrame]] = {}

            df["feature_id"] = None

            for identifier in kit_identifiers:
                kit = session.get_one(Q.feature_kit.select(identifier=identifier))
                kit_df = session.get_pandas(
                    Q.pd.feature_kit_features(kit.id),
                    limit=None,
                )
                kits[identifier] = (kit, kit_df)

            # Auto-fill sequence/pattern/read from kit features
            for identifier, (kit, kit_df) in kits.items():
                in_kit = df["kit"].eq(identifier).fillna(False)
                mask = kit_df["name"].isin(df[in_kit]["feature"])
                for _, kit_row in kit_df[mask].iterrows():
                    df.loc[
                        in_kit & df["feature"].eq(kit_row["name"]).fillna(False),
                        ["sequence", "pattern", "read"]
                    ] = kit_row[["sequence", "pattern", "read"]].values
                    df.loc[
                        in_kit & df["identifier"].eq(kit_row["identifier"]).fillna(False),
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
                    form.spreadsheet.add_error(idx, "kit_id", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "feature", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("duplicate feature definition"))
                    form.spreadsheet.add_error(idx, "read", DuplicateCellValue("duplicate feature definition"))

                if custom_feature.at[idx] and kit_feature.at[idx]:
                    for col in ["kit_id", "feature", "sequence", "pattern", "read"]:
                        form.spreadsheet.add_error(idx, col, InvalidCellValue("must have either 'Kit' or 'Feature + Sequence + Pattern + Read' specified, not both."))

                elif kit_feature.at[idx]:
                    assert row.kit is not None
                    kit, kit_df = kits[row.kit]
                    if row.identifier is not None and row.identifier not in kit_df["identifier"].values:
                        form.spreadsheet.add_error(idx, "identifier", InvalidCellValue(f"Identifier '{row.identifier}' not found in kit '{row.kit}'"))
                        continue
                    if row.feature is not None and row.feature not in kit_df["name"].values:
                        form.spreadsheet.add_error(idx, "feature", InvalidCellValue(f"Feature '{row.feature}' not found in kit '{row.kit}'"))
                        continue

                    match = pd.Series(True, index=kit_df.index)
                    if row.identifier is not None:
                        match &= kit_df["identifier"] == row.identifier
                    if row.feature is not None:
                        match &= kit_df["name"] == row.feature
                    if not match.any():
                        form.spreadsheet.add_error(idx, "feature", InvalidCellValue(f"Identifier '{row.identifier}' and Feature '{row.feature}' refer to different features in kit '{row.kit}'"))
                        continue
                    df.at[idx, "feature_id"] = int(kit_df.loc[match, "feature_id"].iloc[0])

                elif custom_feature.at[idx]:
                    idx_seq = (df["sequence"] == row.sequence) & (df["pattern"] == row.pattern) & (df["read"] == row.read)
                    if df[idx_seq].shape[0] > 1:
                        form.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination."))
                        form.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination."))
                        form.spreadsheet.add_error(idx, "read", DuplicateCellValue("Duplicate 'Sequence + Pattern + Read' combination."))

                else:
                    for col in ["kit_id", "feature", "sequence", "pattern", "read"]:
                        form.spreadsheet.add_error(idx, col, MissingCellValue("must have either 'Kit' (+ 'Feature', optional) or 'Feature + Sequence + Pattern + Read' specified."))

            # Two rows resolving to the same kit feature
            duplicate_kit_feature = df["feature_id"].notna() & df.duplicated(subset=["feature_id"], keep=False)
            for idx in df.index[duplicate_kit_feature]:
                form.spreadsheet.add_error(idx, "feature", DuplicateCellValue("Duplicate 'Kit' + 'Feature' specified."))

            form.assert_valid()

            # Save features
            form.library.features = []

            class FeatureRow(BaseModel):
                feature_id: int | None
                identifier: str | None
                feature: str | None
                sequence: str | None
                pattern: str | None
                read: str | None

            for _, row in parsing.safe_iter(df, FeatureRow):
                if row.feature_id is not None:
                    form.library.features.append(session.get_one(Q.feature.select(id=row.feature_id)))
                else:
                    assert row.feature is not None and row.sequence is not None and row.pattern is not None and row.read is not None
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