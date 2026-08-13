import re
from collections.abc import Iterator

import pandas as pd
from fastapi import Depends

from pydantic import BaseModel

from opengsync_db import models, queries as Q, actions, SyncSession

from ....components import inputs
from ....components.tables import DuplicateCellValue
from ....core import dependencies, exceptions as exc, responses
from ....utils import parsing
from ...HTMXForm import HTMXForm, FormFunc, RouteFunc, htmx_route


class EditKitBarcodesForm(HTMXForm):
    """Shared spreadsheet and persistence behavior for index-kit barcode forms."""

    template_path = "actions/edit-kit-barcodes.html"
    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(allow_new_rows=True)
    reverse_complement_fields: tuple[str, ...] = ()

    def __init__(self, index_kit: models.IndexKit) -> None:
        super().__init__()
        self.index_kit = index_kit
        self._context["index_kit"] = index_kit
        self._context["reverse_complement_inputs"] = [
            getattr(self, field_name) for field_name in self.reverse_complement_fields
        ]
        self.post_url = responses.url_for("EditKitBarcodesForm.Submit", index_kit_id=index_kit.id)

    def barcode_table(self, session: SyncSession) -> pd.DataFrame:
        return session.pd.get_index_kit_barcodes(self.index_kit.id, per_index=True)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            index_kit_id: int,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "EditKitBarcodesForm":
            from . import EDIT_KIT_BARCODES_ACTIONS
            index_kit = session.get_one(Q.index_kit.select(id=index_kit_id))
            try:
                form_class = EDIT_KIT_BARCODES_ACTIONS[index_kit.type]
            except KeyError:
                raise exc.BadRequestException("Unsupported index kit type.")
            form = form_class(index_kit)
            form.spreadsheet.configure(
                csrf_token=form.csrf_token_value,
                post_url=form.post_url,
                df=form.barcode_table(session),
            )
            return form
        return dependency

    @htmx_route("GET", "/{index_kit_id}/edit-barcodes")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "EditKitBarcodesForm" = Depends(EditKitBarcodesForm.Init()),
            _=Depends(dependencies.require_admin),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{index_kit_id}/edit-barcodes")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "EditKitBarcodesForm" = Depends(EditKitBarcodesForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_admin),
        ):
            df = form.spreadsheet.data.copy()
            form.validate_barcodes(df)
            form.assert_valid()
            form.replace_barcodes(session, df)
            return responses.htmx_response(
                redirect=responses.url_for("index_kit_page", index_kit_id=form.index_kit.id),
                flash=responses.flash("Changes saved!", "success"),
            )
        return route

    @staticmethod
    def _clean(value: str | None, *, keep: str = "", spaces: str = "_") -> str | None:
        if value is None:
            return None
        value = re.sub(r"\s+", spaces, str(value).strip())
        return "".join(char for char in value if char.isalnum() or char in keep)

    @staticmethod
    def _normalize_wells(df: pd.DataFrame) -> None:
        wells = df["well"].notna()
        df.loc[wells, "well"] = (
            df.loc[wells, "well"]
            .astype(str)
            .str.strip()
            .str.replace(r"(?<=[A-Z])0+(?=\d)", "", regex=True)
        )

    def _validate_name_sequence_consistency(self, df: pd.DataFrame, index: str) -> None:
        name_column, sequence_column = f"name_{index}", f"sequence_{index}"
        mapped = df[[name_column, sequence_column]].rename(columns={name_column: "name", sequence_column: "sequence"})

        class NameKey(BaseModel):
            name: str

        class SequenceKey(BaseModel):
            sequence: str

        for _, group in parsing.safe_groupby(mapped.dropna(subset=["name"]), "name", NameKey):
            if group["sequence"].nunique(dropna=False) > 1:
                for idx in group.index:
                    self.spreadsheet.add_error(idx, name_column, DuplicateCellValue(f"Duplicate name {index} with different sequence."))

        for _, group in parsing.safe_groupby(mapped.dropna(subset=["sequence"]), "sequence", SequenceKey):
            if group["name"].nunique(dropna=False) > 1:
                for idx in group.index:
                    self.spreadsheet.add_error(idx, sequence_column, DuplicateCellValue(f"Duplicate sequence {index} with different name."))

    def replace_barcodes(self, session: SyncSession, df: pd.DataFrame) -> None:
        self.index_kit = actions.remove_all_barcodes_from_kit(session, self.index_kit)
        barcodes = []
        for adapter, barcode_rows in self.barcode_rows(df):
            session.add(adapter)
            session.flush()
            for row in barcode_rows:
                barcodes.append(Q.barcode.create(adapter=adapter, **row))
        session.add_all(barcodes)

    def barcode_rows(self, df: pd.DataFrame) -> Iterator[tuple[models.Adapter, list[dict]]]:
        raise NotImplementedError

    def validate_barcodes(self, df: pd.DataFrame) -> None:
        raise NotImplementedError
