import pandas as pd
from fastapi import Depends
from sqlalchemy import orm
from pydantic import BaseModel

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ...core import dependencies, responses
from ...utils import parsing
from ...components import inputs
from ...components.tables.spreadsheet import TextColumn, DuplicateCellValue
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class EditKitFeaturesAction(HTMXForm):
    template_path = "forms/edit-kit-features.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        TextColumn("name", "Name", 250, max_length=models.Feature.name.type.length, min_length=3, required=True),
        TextColumn("identifier", "Identifier", 150, max_length=models.Feature.identifier.type.length, required=False),
        TextColumn("sequence", "Sequence", 150, max_length=models.Feature.sequence.type.length, required=True),
        TextColumn("pattern", "Pattern", 200, max_length=models.Feature.pattern.type.length, required=True),
        TextColumn("read", "Read", 100, max_length=models.Feature.read.type.length, required=True),
        TextColumn("target_name", "Target Name", 200, max_length=models.Feature.target_name.type.length, min_length=3, required=False),
        TextColumn("target_id", "Target ID", 200, max_length=models.Feature.target_id.type.length, min_length=3, required=False),
    ])

    def __init__(self, feature_kit: models.FeatureKit) -> None:
        super().__init__()
        self.feature_kit = feature_kit
        self._context["feature_kit"] = feature_kit
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", feature_kit_id=feature_kit.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            feature_kit_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "EditKitFeaturesAction":
            feature_kit = session.get_one(
                Q.feature_kit.select(id=feature_kit_id),
                options=[orm.selectinload(models.FeatureKit.features)],
            )
            form = EditKitFeaturesAction(feature_kit=feature_kit)
            df = session.pd.get_feature_kit_features(feature_kit.id)
            form.spreadsheet.configure(
                csrf_token=form.csrf_token_value,
                post_url=form.post_url,
                df=df,
            )
            return form
        return dependency

    @htmx_route("GET", "/{feature_kit_id}/edit-features")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "EditKitFeaturesAction" = Depends(EditKitFeaturesAction.Init()),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{feature_kit_id}/edit-features")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "EditKitFeaturesAction" = Depends(EditKitFeaturesAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_insider),
        ):
            df = form.spreadsheet.data

            duplicate_def = df.duplicated(subset=["sequence", "pattern", "read"], keep=False)
            duplicate_feature = df.duplicated(subset=["name"], keep=False) & (form.feature_kit.type in [C.FeatureType.CMO])

            for idx, row in df.iterrows():
                if duplicate_feature.at[idx]:
                    form.spreadsheet.add_error(idx, "name", DuplicateCellValue(f"Duplicate feature name not allowed in '{form.feature_kit.type.name}'-kit."))
                if duplicate_def.at[idx]:
                    form.spreadsheet.add_error(idx, "sequence", DuplicateCellValue("Duplicate sequence + pattern + read combination."))
                    form.spreadsheet.add_error(idx, "pattern", DuplicateCellValue("Duplicate sequence + pattern + read combination."))
                    form.spreadsheet.add_error(idx, "read", DuplicateCellValue("Duplicate sequence + pattern + read combination."))

            form.assert_valid()

            df = df.sort_values("name")

            form.feature_kit.features = []
            class RowSchema(BaseModel):
                identifier: str | None
                name: str
                sequence: str
                pattern: str
                read: str
                target_name: str | None
                target_id: str | None

            for _, row in parsing.safe_iter(df, RowSchema):
                form.feature_kit.features.append(
                    Q.feature.create(
                        identifier=row.identifier,
                        name=row.name,
                        sequence=row.sequence,
                        pattern=row.pattern,
                        read=row.read,
                        target_name=row.target_name,
                        target_id=row.target_id,
                        feature_kit_id=form.feature_kit.id,
                        type=form.feature_kit.type,
                    )
                )

            session.save(form.feature_kit)

            return responses.htmx_response(
                redirect=responses.url_for("feature_kit_page", feature_kit_id=form.feature_kit.id),
                flash=responses.flash("Changes saved!", "success"),
            )
        return route