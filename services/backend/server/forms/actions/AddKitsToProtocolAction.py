import pandas as pd
from fastapi import Depends

from opengsync_db import models, queries as Q, SyncSession

from ...core import dependencies, responses
from ...components import inputs
from ...components.tables.spreadsheet import IntegerColumn, MissingCellValue, DuplicateCellValue
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm
from ..common import kit_columns


class AddKitsToProtocolAction(HTMXForm):
    template_path = "workflows/add_kits_to_protocol/add-kit-combinations.html"

    spreadsheet = inputs.spreadsheet.SpreadsheetInputField(columns=[
        kit_columns.kit_column("kit_id", "Kit", 600, required=True),
        IntegerColumn("combination_num", "Combination", 200, required=False),
    ])

    def __init__(self, protocol: models.Protocol) -> None:
        super().__init__()
        self.protocol = protocol
        self._context["protocol"] = protocol
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", protocol_id=protocol.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            protocol_id: int,
            _=Depends(dependencies.require_insider),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "AddKitsToProtocolAction":
            protocol = session.get_one(Q.protocol.select(id=protocol_id))

            form = AddKitsToProtocolAction(protocol=protocol)

            # Pre-fill with the protocol's current kit combinations
            df = session.get_pandas(Q.pd.protocol_kits(protocol_id=protocol.id), limit=None)
            form.spreadsheet.configure(csrf_token=form.csrf_token_value, post_url=form.post_url, df=df)
            return form
        return dependency

    @htmx_route("GET", "/{protocol_id}/add-kits")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "AddKitsToProtocolAction" = Depends(AddKitsToProtocolAction.Init()),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{protocol_id}/add-kits")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "AddKitsToProtocolAction" = Depends(AddKitsToProtocolAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            df = form.spreadsheet.data

            if df["combination_num"].isna().all():
                df["combination_num"] = 1

            duplicate = df.duplicated(subset=["kit_id", "combination_num"], keep=False)

            for idx, row in df.iterrows():
                if duplicate.at[idx]:
                    form.spreadsheet.add_error(idx, "kit_id", DuplicateCellValue("Duplicate kit and combination number."))
                if pd.isna(row["combination_num"]):
                    form.spreadsheet.add_error(idx, "combination_num", MissingCellValue("Combination number is required."))

            form.assert_valid()

            form.protocol.kit_links = []
        
            for _, row in df.iterrows():
                form.protocol.kit_links.append(
                    models.links.ProtocolKitLink(
                        protocol_id=form.protocol.id,
                        kit_id=int(row["kit_id"]),
                        combination_num=int(row["combination_num"]),
                    )
                )

            session.save(form.protocol)

            return responses.htmx_response(
                redirect=responses.url_for("protocol_page", protocol_id=form.protocol.id).include_query_params(tab="protocol-kits-tab"),
                flash=responses.flash("Changes Saved!", "success"),
            )
                
        return route